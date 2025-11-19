from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.services.github.github_sync import sync_user_available_repos
from app.tasks.ingestion import process_workflow_run


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
                "$setOnInsert": {"_id": installation_id, "created_at": now},
            },
            upsert=True,
        )
        return {
            "status": "processed",
            "action": "installation_created",
            "installation_id": installation_id,
        }

    elif action == "created" or action == "added" or action == "removed":
        # For installation_repositories event, action is 'added' or 'removed'
        pass

    elif action == "deleted":
        # User uninstalled the app
        db.github_installations.update_one(
            {"_id": installation_id},
            {"$set": {"revoked_at": now, "uninstalled_at": now}},
        )
        # Clear cached token
        from app.services.github_app import clear_installation_token

        clear_installation_token(installation_id)
        return {
            "status": "processed",
            "action": "installation_deleted",
            "installation_id": installation_id,
        }

    elif action == "suspend":
        db.github_installations.update_one(
            {"_id": installation_id}, {"$set": {"suspended_at": now}}
        )
        from app.services.github_app import clear_installation_token

        clear_installation_token(installation_id)
        return {
            "status": "processed",
            "action": "installation_suspended",
            "installation_id": installation_id,
        }

    elif action == "unsuspend":
        db.github_installations.update_one(
            {"_id": installation_id}, {"$set": {"suspended_at": None}}
        )
        return {
            "status": "processed",
            "action": "installation_unsuspended",
            "installation_id": installation_id,
        }

    return {"status": "ignored", "reason": f"unsupported_installation_action: {action}"}

    return {"status": "ignored", "reason": f"unsupported_installation_action: {action}"}


def _handle_workflow_run_event(
    db: Database, payload: Dict[str, object]
) -> Dict[str, object]:
    """Handle workflow_run events."""
    action = payload.get("action")
    # We usually care about 'completed' to get logs, but maybe 'in_progress' too?
    # For logs, we need it to be completed usually, or at least jobs completed.
    # Let's process 'completed' for now to ensure logs are ready.
    if action != "completed":
        return {"status": "ignored", "reason": f"action_{action}_not_supported_yet"}

    repo_data = payload.get("repository", {})
    full_name = repo_data.get("full_name")
    workflow_run = payload.get("workflow_run", {})

    if not full_name or not workflow_run:
        return {"status": "ignored", "reason": "missing_data"}

    # Check if we are tracking this repo
    repo = db.repositories.find_one({"full_name": full_name})
    if not repo:
        return {"status": "ignored", "reason": "repo_not_imported"}

    repo_id = str(repo["_id"])

    # Trigger processing
    process_workflow_run.delay(repo_id, workflow_run)

    return {
        "status": "processed",
        "action": "workflow_run_queued",
        "repo_id": repo_id,
        "run_id": workflow_run.get("id"),
    }


def handle_github_event(
    db: Database, event: str, payload: Dict[str, object]
) -> Dict[str, object]:
    if event in {"installation", "installation_repositories"}:
        result = _handle_installation_event(db, event, payload)

        # Trigger Sync for the user who initiated this
        sender = payload.get("sender", {})
        sender_login = sender.get("login")

        if sender_login:
            # Find user by GitHub login
            # We need to find the user who has this GitHub account linked
            identity = db.oauth_identities.find_one(
                {
                    "$or": [
                        {"account_login": sender_login},
                        {"profile.login": sender_login},
                    ]
                }
            )

            if identity:
                user_id = str(identity["user_id"])
                try:
                    sync_user_available_repos(db, user_id)
                    result["sync_triggered"] = True
                    result["user_id"] = user_id
                except Exception as e:
                    result["sync_error"] = str(e)

        return result

    elif event == "workflow_run":
        return _handle_workflow_run_event(db, payload)

    return {"status": "ignored", "reason": "event_not_handled"}
