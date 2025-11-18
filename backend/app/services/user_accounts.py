from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from pymongo.database import Database

PROVIDER_GITHUB = "github"


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
    # Additional metadata to store on the identity
    account_login: Optional[str] = None,
    account_name: Optional[str] = None,
    account_avatar_url: Optional[str] = None,
    connected_at: Optional[datetime] = None,
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
                    "account_login": account_login,
                    "account_name": account_name,
                    "account_avatar_url": account_avatar_url,
                    "connected_at": connected_at,
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
        identity_doc = (
            identities.find_one({"_id": existing_identity["_id"]}) or existing_identity
        )
        return user_doc, identity_doc

    result = users.insert_one(
        {"email": email, "name": name, "role": "user", "created_at": now}
    )
    user_doc = users.find_one({"_id": result.inserted_id})

    identity_doc = {
        "user_id": user_doc["_id"],
        "provider": PROVIDER_GITHUB,
        "external_user_id": github_user_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "scopes": scopes,
        "account_login": account_login,
        "account_name": account_name,
        "account_avatar_url": account_avatar_url,
        "connected_at": connected_at,
        "created_at": now,
    }
    identity_result = identities.insert_one(identity_doc)
    identity_doc = identities.find_one({"_id": identity_result.inserted_id})
    # Return the user and freshly created identity documents.

    return user_doc, identity_doc


def list_users(db: Database) -> list[Dict[str, object]]:
    return list(db.users.find().sort("created_at", -1))
