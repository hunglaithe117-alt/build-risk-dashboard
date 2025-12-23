from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.celery_app import celery_app
from app.ci_providers.models import BuildConclusion, BuildStatus, CIProvider
from app.config import settings
from app.entities.raw_build_run import RawBuildRun
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository


def verify_signature(signature: str | None, body: bytes) -> None:
    if not settings.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook secret is not configured on the server.",
        )

    if not signature or not signature.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
        )

    digest = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    expected = f"sha256={digest}"
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook signature mismatch",
        )


def _handle_workflow_run_event(
    db: Database, payload: Dict[str, object]
) -> Dict[str, object]:
    """Handle workflow_run events."""
    action = payload.get("action")
    # Only process completed runs; we additionally filter by conclusion below.
    if action != "completed":
        return {"status": "ignored", "reason": f"action_{action}_not_supported_yet"}

    repo_data = payload.get("repository", {})
    full_name = repo_data.get("full_name")
    workflow_run = payload.get("workflow_run", {})

    if not full_name or not workflow_run:
        return {"status": "ignored", "reason": "missing_data"}
    # Accept only runs whose conclusion is completed; status can vary.
    conclusion_val = (workflow_run.get("conclusion") or "").lower()
    if conclusion_val != "completed":
        return {"status": "ignored", "reason": f"conclusion_{conclusion_val}_ignored"}

    # Filter out bot-triggered workflow runs (e.g., Dependabot, github-actions[bot])
    triggering_actor = workflow_run.get("triggering_actor", {})
    actor_type = triggering_actor.get("type")
    is_bot = actor_type == "Bot"

    # Check if we are tracking this repo
    raw_repo = RawRepositoryRepository(db)
    repo = raw_repo.find_one({"full_name": full_name})
    if not repo:
        return {"status": "ignored", "reason": "repo_not_imported"}

    repo_id = str(repo.id)
    build_id = str(workflow_run.get("id"))

    # Save/Update RawBuildRun
    build_run_repo = RawBuildRunRepository(db)

    existing_run = build_run_repo.find_by_business_key(
        repo_id, build_id, CIProvider.GITHUB
    )

    if existing_run:
        # Update existing run but don't reprocess (avoid duplicate processing)
        completed_at = workflow_run.get("updated_at")
        build_run_repo.update_one(
            str(existing_run.id),
            {
                "status": BuildStatus.COMPLETED,
                "conclusion": workflow_run.get("conclusion"),
                "completed_at": (
                    datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                    if completed_at
                    else datetime.now(timezone.utc)
                ),
                "raw_data": workflow_run,
            },
        )
        return {
            "status": "updated",
            "action": "build_run_updated",
            "repo_id": repo_id,
            "build_id": build_id,
        }
    else:
        # New build run - insert and trigger processing
        created_at = workflow_run.get("created_at")
        completed_at = workflow_run.get("updated_at")

        # Map GitHub status to normalized status
        status = BuildStatus.COMPLETED

        # Map GitHub conclusion to normalized conclusion
        gh_conclusion = workflow_run.get("conclusion", "").lower()
        try:
            conclusion = (
                BuildConclusion(gh_conclusion)
                if gh_conclusion
                else BuildConclusion.NONE
            )
        except (ValueError, KeyError):
            conclusion = BuildConclusion.UNKNOWN

        new_run = RawBuildRun(
            raw_repo_id=ObjectId(repo_id),
            build_id=build_id,
            build_number=workflow_run.get("run_number"),
            repo_name=full_name,
            branch=workflow_run.get("head_branch", ""),
            commit_sha=workflow_run.get("head_sha", ""),
            commit_message=None,
            commit_author=None,
            status=status,
            conclusion=conclusion,
            created_at=(
                datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created_at
                else datetime.now(timezone.utc)
            ),
            started_at=None,
            completed_at=(
                datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
                if completed_at
                else datetime.now(timezone.utc)
            ),
            duration_seconds=None,
            web_url=workflow_run.get("html_url"),
            logs_url=None,
            logs_available=False,
            logs_path=None,
            provider=CIProvider.GITHUB_ACTIONS,
            raw_data=workflow_run,
            is_bot_commit=is_bot,
        )
        inserted_run = build_run_repo.create(new_run)

        db.repositories.update_one(
            {"_id": ObjectId(repo_id)}, {"$inc": {"total_builds_imported": 1}}
        )

        # Find ModelRepoConfig for this raw_repo
        from app.repositories.model_repo_config import ModelRepoConfigRepository

        model_repo_config_repo = ModelRepoConfigRepository(db)
        repo_config = model_repo_config_repo.find_active_by_raw_repo_id(
            ObjectId(repo_id)
        )

        if not repo_config:
            return {
                "status": "processed",
                "action": "build_run_created_no_config",
                "repo_id": repo_id,
                "build_id": build_id,
                "message": "RawBuildRun created but no ModelRepoConfig found for processing",
            }

        repo_config_id = str(repo_config.id)

        # Dispatch prepare_and_dispatch_processing to run ingestion workflow (clone, logs, worktrees)
        # then dispatch_build_processing for feature extraction
        # This aligns webhook flow with import flow
        celery_app.send_task(
            "app.tasks.model_ingestion.prepare_and_dispatch_processing",
            kwargs={
                "repo_config_id": repo_config_id,
                "raw_repo_id": repo_id,
                "full_name": full_name,
                "ci_provider": (
                    repo_config.ci_provider.value
                    if hasattr(repo_config.ci_provider, "value")
                    else repo_config.ci_provider
                ),
                "ci_build_ids": [build_id],  # Single build from webhook
            },
        )

    return {
        "status": "processed",
        "action": "build_run_queued",
        "repo_id": repo_id,
        "build_id": build_id,
    }


def handle_github_event(
    db: Database, event: str, payload: Dict[str, object]
) -> Dict[str, object]:
    if event in {"installation", "installation_repositories"}:
        # return _handle_installation_event(db, event, payload)
        return {"status": "ignored", "reason": "installation_management_removed"}

    elif event == "workflow_run":
        return _handle_workflow_run_event(db, payload)

    return {"status": "ignored", "reason": "event_not_handled"}
