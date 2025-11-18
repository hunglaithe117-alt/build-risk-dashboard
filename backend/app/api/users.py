"""User management helper endpoints (role definitions, login)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Response
from app.services.auth import create_access_token
from pymongo.database import Database

from app.database.mongo import get_db
from app.models.schemas import (
    GithubLoginRequest,
    OAuthIdentityResponse,
    UserLoginResponse,
    UserResponse,
)
from app.services.user_accounts import (
    PROVIDER_GITHUB,
    list_users as list_users_service,
    upsert_github_identity,
)
from app.config import settings

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/", response_model=List[UserResponse])
def list_users(db: Database = Depends(get_db)):
    documents = list_users_service(db)
    return [UserResponse.model_validate(doc) for doc in documents]


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
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub token"
            ) from exc

        user_data = user_response.json()
        email = user_data.get("email")
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails", headers=headers
            )
            emails_response.raise_for_status()
            emails = emails_response.json()
            primary = next(
                (item.get("email") for item in emails if item.get("primary")), None
            )
            fallback = emails[0]["email"] if emails else None
            email = primary or fallback
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to retrieve email from GitHub user",
            )
        user_data["resolved_email"] = email
        return user_data


@router.post("/github/login", response_model=UserLoginResponse)
async def github_login(payload: GithubLoginRequest, db: Database = Depends(get_db), response: Response = None):
    profile = await _fetch_github_profile(payload.access_token)
    external_id = profile.get("id")
    if not external_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Did not receive GitHub user id",
        )
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
        account_login=profile.get("login"),
        account_name=profile.get("name"),
        account_avatar_url=profile.get("avatar_url"),
    )
    token = create_access_token(subject=user_doc["_id"])
    if response is not None:
        response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    return {
        "user": UserResponse.model_validate(user_doc),
        "identity": OAuthIdentityResponse.model_validate(identity_doc),
    }


@router.get("/me", response_model=UserResponse)
def get_current_user(db: Database = Depends(get_db)):
    # Find an OAuth identity for GitHub and use the linked user document.
    identity = db.oauth_identities.find_one({"provider": PROVIDER_GITHUB})
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user is currently logged in.",
        )

    user_doc = db.users.find_one({"_id": identity["user_id"]})

    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user found for the current GitHub connection.",
        )

    return UserResponse.model_validate(user_doc)
