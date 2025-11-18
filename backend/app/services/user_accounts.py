"""Persistence helpers for user accounts and OAuth identities."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from pymongo.database import Database

PROVIDER_GITHUB = "github"


def _generate_numeric_id(collection) -> int:
    latest = collection.find_one(sort=[("_id", -1)])
    if latest:
        return int(latest.get("_id", 0)) + 1
    return 1


def _serialize_user(document: Dict[str, object]) -> Dict[str, object]:
    payload = document.copy()
    payload["id"] = payload.pop("_id")
    return payload


def _serialize_identity(document: Dict[str, object]) -> Dict[str, object]:
    payload = document.copy()
    payload["id"] = payload.pop("_id")
    return payload


def upsert_github_identity(
    db: Database,
    *,
    github_user_id: str,
    email: str,
    name: Optional[str],
    access_token: str,
    refresh_token: Optional[str],
    token_expires_at: Optional[datetime],
    scopes: Optional[str],
) -> Tuple[Dict[str, object], Dict[str, object]]:
    users = db.users
    identities = db.oauth_identities

    existing_identity = identities.find_one(
        {"provider": PROVIDER_GITHUB, "external_user_id": github_user_id}
    )

    now = datetime.now(timezone.utc)

    if existing_identity:
        identities.update_one(
            {"_id": existing_identity["_id"]},
            {
                "$set": {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_expires_at": token_expires_at,
                    "scopes": scopes,
                    "updated_at": now,
                }
            },
        )
        user_doc = users.find_one({"_id": existing_identity["user_id"]})
        if not user_doc:
            raise ValueError("User referenced by identity not found")
        if user_doc and email and user_doc.get("email") != email:
            users.update_one({"_id": user_doc["_id"]}, {"$set": {"email": email}})
            user_doc["email"] = email
        if user_doc and name and user_doc.get("name") != name:
            users.update_one({"_id": user_doc["_id"]}, {"$set": {"name": name}})
            user_doc["name"] = name
        identity_doc = identities.find_one({"_id": existing_identity["_id"]}) or existing_identity
        return user_doc, identity_doc

    user_id = _generate_numeric_id(users)
    user_doc = {
        "_id": user_id,
        "email": email,
        "name": name,
        "role": "user",
        "created_at": now,
    }
    users.insert_one(user_doc)

    identity_id = _generate_numeric_id(identities)
    identity_doc = {
        "_id": identity_id,
        "user_id": user_id,
        "provider": PROVIDER_GITHUB,
        "external_user_id": github_user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "scopes": scopes,
        "created_at": now,
    }
    identities.insert_one(identity_doc)

    return user_doc, identity_doc


def list_users(db: Database) -> list[Dict[str, object]]:
    return list(db.users.find().sort("created_at", -1))
