from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.repositories.workflow_run import WorkflowRunRepository
from app.entities.workflow_run import WorkflowRunRaw
from app.celery_app import celery_app
from bson import ObjectId
from app.services.github.github_app import clear_installation_token


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


def _handle_installation_event(
    db: Database, event: str, payload: Dict[str, object]
) -> Dict[str, object]:
    """Handle GitHub App installation/uninstallation events."""
    action = payload.get("action")
    installation = payload.get("installation", {})
    installation_id = str(installation.get("id")) if installation.get("id") else None
    account = installation.get("account", {})
    account_login = account.get("login")
    account_type = account.get("type")  # "User" or "Organization"

    if not installation_id:
        return {"status": "ignored", "reason": "missing_installation_id"}

    now = datetime.now(timezone.utc)

    if action == "created":
        # User installed the app
        db.github_installations.update_one(
            {"installation_id": installation_id},
            {
                "$set": {
                    "installation_id": installation_id,
                    "account_login": account_login,
                    "account_type": account_type,
                    "installed_at": now,
                    "revoked_at": None,
                    "suspended_at": None,
                    "metadata": installation,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return {
            "status": "processed",
            "action": "installation_created",
            "installation_id": installation_id,
        }

    elif action == "added" or action == "removed":
        # For installation_repositories event, action is 'added' or 'removed'
        pass

    elif action == "deleted":
        # User uninstalled the app
        db.github_installations.update_one(
            {"installation_id": installation_id},
            {"$set": {"revoked_at": now, "uninstalled_at": now}},
        )
        # Clear cached token

        clear_installation_token(installation_id)
        return {
            "status": "processed",
            "action": "installation_deleted",
            "installation_id": installation_id,
        }

    elif action == "suspend":
        db.github_installations.update_one(
            {"installation_id": installation_id}, {"$set": {"suspended_at": now}}
        )

        clear_installation_token(installation_id)
        return {
            "status": "processed",
            "action": "installation_suspended",
            "installation_id": installation_id,
        }

    elif action == "unsuspend":
        db.github_installations.update_one(
            {"installation_id": installation_id}, {"$set": {"suspended_at": None}}
        )
        return {
            "status": "processed",
            "action": "installation_unsuspended",
            "installation_id": installation_id,
        }

    return {"status": "ignored", "reason": f"unsupported_installation_action: {action}"}


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
    if actor_type == "Bot":
        return {"status": "ignored", "reason": "bot_triggered"}

    # Check if we are tracking this repo
    repo = db.repositories.find_one({"full_name": full_name})
    if not repo:
        return {"status": "ignored", "reason": "repo_not_imported"}

    repo_id = str(repo["_id"])
    run_id = workflow_run.get("id")

    # Save/Update WorkflowRunRaw
    workflow_run_repo = WorkflowRunRepository(db)

    existing_run = workflow_run_repo.find_by_repo_and_run_id(repo_id, run_id)

    if existing_run:
        # Update existing run but don't reprocess (avoid duplicate processing)
        updated_at = workflow_run.get("updated_at")
        workflow_run_repo.update_one(
            str(existing_run.id),
            {
                "status": workflow_run.get("status"),
                "conclusion": workflow_run.get("conclusion"),
                "updated_at": (
                    datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    if updated_at
                    else datetime.now(timezone.utc)
                ),
                "raw_payload": workflow_run,
            },
        )
        return {
            "status": "updated",
            "action": "workflow_run_updated",
            "repo_id": repo_id,
            "run_id": run_id,
        }
    else:
        # New workflow run - insert and trigger processing
        created_at = workflow_run.get("created_at")
        updated_at = workflow_run.get("updated_at")
        from app.entities.workflow_run import WorkflowRunStatus, WorkflowConclusion

        status = workflow_run.get("status")
        try:
            status_enum = (
                WorkflowRunStatus(status)
                if status
                else WorkflowRunStatus.UNKNOWN
            )
        except Exception:
            status_enum = WorkflowRunStatus.UNKNOWN

        conclusion = workflow_run.get("conclusion")
        try:
            conclusion_enum = (
                WorkflowConclusion(conclusion)
                if conclusion
                else WorkflowConclusion.UNKNOWN
            )
        except Exception:
            conclusion_enum = WorkflowConclusion.UNKNOWN

        new_run = WorkflowRunRaw(
            repo_id=ObjectId(repo_id),
            workflow_run_id=run_id,
            head_sha=workflow_run.get("head_sha"),
            run_number=workflow_run.get("run_number"),
            status=status_enum,
            conclusion=conclusion_enum,
            ci_created_at=(
                datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created_at
                else datetime.now(timezone.utc)
            ),
            ci_updated_at=(
                datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if updated_at
                else datetime.now(timezone.utc)
            ),
            raw_payload=workflow_run,
            branch=workflow_run.get("head_branch"),
        )
        workflow_run_repo.insert_one(new_run)

        db.repositories.update_one(
            {"_id": ObjectId(repo_id)}, {"$inc": {"total_builds_imported": 1}}
        )

    celery_app.send_task(
        "app.tasks.processing.process_workflow_run", args=[repo_id, run_id]
    )

    return {
        "status": "processed",
        "action": "workflow_run_queued",
        "repo_id": repo_id,
        "run_id": run_id,
    }


def handle_github_event(
    db: Database, event: str, payload: Dict[str, object]
) -> Dict[str, object]:
    if event in {"installation", "installation_repositories"}:
        return _handle_installation_event(db, event, payload)

    elif event == "workflow_run":
        return _handle_workflow_run_event(db, payload)

    return {"status": "ignored", "reason": "event_not_handled"}
