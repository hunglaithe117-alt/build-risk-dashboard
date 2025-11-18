"""GitHub OAuth helper utilities (MongoDB)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.services.user_service import upsert_github_identity

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


async def verify_github_token(access_token: str) -> bool:
    """Verify if a GitHub access token is still valid."""
    if not access_token:
        return False
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                GITHUB_USER_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            return response.status_code == 200
    except Exception:
        return False


def _require_github_credentials() -> None:
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub OAuth credentials are not configured. Set GITHUB_CLIENT_ID/SECRET.",
        )


def build_authorize_url(state: str) -> str:
    scopes = settings.GITHUB_SCOPES
    scope_param = " ".join(scopes)
    return (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope={scope_param}"
        f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
        f"&state={state}"
    )


def create_oauth_state(db: Database, redirect_url: Optional[str] = None) -> dict:
    _require_github_credentials()
    state = uuid.uuid4().hex
    document = {
        "_id": state,
        "redirect_url": redirect_url,
        "created_at": datetime.now(timezone.utc),
        "used": False,
        "used_at": None,
    }
    db.github_states.insert_one(document)
    return document


async def exchange_code_for_token(
    db: Database, code: str, state: str
) -> Tuple[dict, Optional[str]]:
    _require_github_credentials()

    oauth_state = db.github_states.find_one({"_id": state, "used": False})
    if not oauth_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        )

    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GITHUB_REDIRECT_URI,
                "state": state,
            },
        )
    token_response.raise_for_status()
    token_data = token_response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub did not return an access token",
        )

    scope = token_data.get("scope")

    async with httpx.AsyncClient(timeout=10) as client:
        user_response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        user_response.raise_for_status()
        user_data = user_response.json()

        email = user_data.get("email")
        if not email:
            try:
                emails_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {access_token}",
                    },
                )
                emails_response.raise_for_status()
                emails = emails_response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                emails = []
            primary = next(
                (item.get("email") for item in emails if item.get("primary")), None
            )
            fallback = emails[0]["email"] if emails else None
            email = primary or fallback

    if not email:
        login = user_data.get("login")
        if login:
            email = f"{login}@users.noreply.github.com"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to retrieve email from GitHub user",
            )

    github_user_id = user_data.get("id")
    if not github_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub did not return user id",
        )

    user_doc, identity_doc = upsert_github_identity(
        db,
        github_user_id=str(github_user_id),
        email=email,
        name=user_data.get("name") or user_data.get("login"),
        access_token=access_token,
        refresh_token=None,
        token_expires_at=None,
        scopes=scope,
        account_login=user_data.get("login"),
        account_name=user_data.get("name"),
        account_avatar_url=user_data.get("avatar_url"),
        connected_at=datetime.now(timezone.utc),
    )
    db.github_states.update_one(
        {"_id": state},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}},
    )

    redirect_url = oauth_state.get("redirect_url")
    # Return identity doc (used in other handlers) and optional redirect path
    return identity_doc, redirect_url
