"""User management helper endpoints (role definitions, login)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.models.schemas import (
    GithubLoginRequest,
    OAuthIdentityResponse,
    RoleListResponse,
    UserLoginResponse,
    UserResponse,
)
from app.services.user_accounts import (
    PROVIDER_GITHUB,
    list_users as list_users_service,
    upsert_github_identity,
)

router = APIRouter(prefix="/users", tags=["Users"])

ROLE_DEFINITIONS = [
    {
        "role": "admin",
        "description": "Manage users and system configuration.",
        "permissions": [
            "manage_repositories",
            "configure_settings",
            "view_logs",
        ],
        "admin_only": True,
    },
    {
        "role": "user",
        "description": "Log in with GitHub to view the dashboard and receive alerts.",
        "permissions": [
            "view_dashboard",
            "receive_alerts",
        ],
        "admin_only": False,
    },
]


def _serialize_user(doc: dict) -> UserResponse:
    return UserResponse.model_validate(doc)


def _serialize_identity(doc: dict) -> OAuthIdentityResponse:
    return OAuthIdentityResponse.model_validate(doc)


@router.get("/roles", response_model=RoleListResponse)
def list_roles():
    return {"roles": ROLE_DEFINITIONS}


@router.get("/", response_model=List[UserResponse])
def list_users(db: Database = Depends(get_db)):
    documents = list_users_service(db)
    return [_serialize_user(doc) for doc in documents]


async def _fetch_github_profile(access_token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        user_response = await client.get("https://api.github.com/user", headers=headers)
        try:
            user_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub token") from exc

        user_data = user_response.json()
        email = user_data.get("email")
        if not email:
            emails_response = await client.get("https://api.github.com/user/emails", headers=headers)
            emails_response.raise_for_status()
            emails = emails_response.json()
            primary = next((item.get("email") for item in emails if item.get("primary")), None)
            fallback = emails[0]["email"] if emails else None
            email = primary or fallback
        if not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to retrieve email from GitHub user")
        user_data["resolved_email"] = email
        return user_data


@router.post("/github/login", response_model=UserLoginResponse)
async def github_login(payload: GithubLoginRequest, db: Database = Depends(get_db)):
    profile = await _fetch_github_profile(payload.access_token)
    external_id = profile.get("id")
    if not external_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Did not receive GitHub user id")
    expires_at = None
    if payload.expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.expires_in)

    user_doc, identity_doc = upsert_github_identity(
        db,
        github_user_id=str(external_id),
        email=profile.get("resolved_email"),
        name=profile.get("name") or profile.get("login"),
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
        token_expires_at=expires_at,
        scopes=payload.scope,
    )

    return {
        "user": _serialize_user(user_doc),
        "identity": _serialize_identity(identity_doc),
    }


@router.get("/me", response_model=UserResponse)
def get_current_user(db: Database = Depends(get_db)):
    connection = db.github_connection.find_one({})
    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user is currently logged in.",
        )

    user_doc = None
    user_id = connection.get("user_id")
    if user_id is not None:
        user_doc = db.users.find_one({"_id": user_id})

    if user_doc is None:
        github_user_id = connection.get("github_user_id")
        if github_user_id:
            identity = db.oauth_identities.find_one(
                {"provider": PROVIDER_GITHUB, "external_user_id": str(github_user_id)}
            )
            if identity:
                user_doc = db.users.find_one({"_id": identity["user_id"]})

    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found for the current GitHub connection.",
        )

    return _serialize_user(user_doc)
