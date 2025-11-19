"""Helpers for handling GitHub webhook events."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings


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
    if event in {"installation", "installation_repositories"}:
        return _handle_installation_event(db, event, payload)

    # All other webhook events are ignored because workflow ingestion is disabled.
    return {"status": "ignored", "reason": "workflow_handling_disabled"}
