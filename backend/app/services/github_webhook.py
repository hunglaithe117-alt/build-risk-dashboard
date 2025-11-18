"""Helpers for handling GitHub webhook events for workflow runs."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.services.github_client import get_pipeline_github_client
from app.services.pipeline_store import PipelineStore


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def verify_signature(signature: str | None, body: bytes) -> None:
    if not settings.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook secret is not configured on the server.",
        )

    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    digest = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    expected = f"sha256={digest}"
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook signature mismatch")


def _actor_login(payload: Dict[str, object]) -> Optional[str]:
    actor = payload.get("workflow_run", {}).get("actor") or payload.get("sender")
    if isinstance(actor, dict):
        login = actor.get("login")
        return login.lower() if login else None
    if isinstance(actor, str):
        return actor.lower()
    return None


def _handle_installation_event(db: Database, event: str, payload: Dict[str, object]) -> Dict[str, object]:
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
            {"_id": installation_id},
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
                "$setOnInsert": {"_id": installation_id, "created_at": now}
            },
            upsert=True,
        )
        return {"status": "processed", "action": "installation_created", "installation_id": installation_id}
    
    elif action == "deleted":
        # User uninstalled the app
        db.github_installations.update_one(
            {"_id": installation_id},
            {"$set": {"revoked_at": now, "uninstalled_at": now}}
        )
        # Clear cached token
        from app.services.github_app import clear_installation_token
        clear_installation_token(installation_id)
        return {"status": "processed", "action": "installation_deleted", "installation_id": installation_id}
    
    elif action == "suspend":
        db.github_installations.update_one(
            {"_id": installation_id},
            {"$set": {"suspended_at": now}}
        )
        from app.services.github_app import clear_installation_token
        clear_installation_token(installation_id)
        return {"status": "processed", "action": "installation_suspended", "installation_id": installation_id}
    
    elif action == "unsuspend":
        db.github_installations.update_one(
            {"_id": installation_id},
            {"$set": {"suspended_at": None}}
        )
        return {"status": "processed", "action": "installation_unsuspended", "installation_id": installation_id}
    
    return {"status": "ignored", "reason": f"unsupported_installation_action: {action}"}


def handle_github_event(db: Database, event: str, payload: Dict[str, object]) -> Dict[str, object]:
    # Handle GitHub App installation events
    if event in {"installation", "installation_repositories"}:
        return _handle_installation_event(db, event, payload)
    
    if event != "workflow_run":
        return {"status": "ignored", "reason": "unsupported_event"}

    if payload.get("action") != "completed":
        return {"status": "ignored", "reason": "non_completed_action"}

    workflow_run = payload.get("workflow_run") or {}
    repository = payload.get("repository") or workflow_run.get("repository") or {}
    full_name = repository.get("full_name")
    if not full_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thiếu repository full_name trong payload")

    run_id = workflow_run.get("id")
    if not run_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Thiếu workflow_run id")

    actor_login = _actor_login(payload)
    if actor_login and "dependabot" in actor_login:
        return {"status": "ignored", "reason": "dependabot"}

    installation = payload.get("installation") or {}
    installation_id_raw = installation.get("id")
    installation_id = str(installation_id_raw) if installation_id_raw is not None else None

    with get_pipeline_github_client(db, installation_id) as gh:
        if not gh.logs_available(full_name, run_id):
            return {"status": "skipped", "reason": "logs_expired"}

    store = PipelineStore(db)
    document = {
        "_id": run_id,
        "repository": full_name,
        "branch": workflow_run.get("head_branch"),
        "status": workflow_run.get("status"),
        "conclusion": workflow_run.get("conclusion"),
        "event": payload.get("action"),
        "installation_id": installation_id,
        "created_at": _parse_datetime(workflow_run.get("created_at")),
        "started_at": _parse_datetime(workflow_run.get("run_started_at")),
        "updated_at": _parse_datetime(workflow_run.get("updated_at")),
        "logs_url": workflow_run.get("logs_url"),
        "check_suite_id": workflow_run.get("check_suite_id"),
        "display_title": workflow_run.get("display_title"),
        "head_sha": workflow_run.get("head_sha"),
        "actor": workflow_run.get("actor") or payload.get("sender"),
        "pull_requests": workflow_run.get("pull_requests", []),
    }
    store.upsert_workflow_run(run_id, document)

    from app.tasks.builds import ingest_workflow_run  # local import to avoid circular dependency

    ingest_workflow_run.delay(full_name, run_id, None)
    return {"status": "queued", "build_id": run_id}
