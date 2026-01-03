"""GitHub OAuth helper utilities (MongoDB)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.entities.oauth_identity import OAuthIdentity
from app.services.user_service import upsert_github_identity

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_ORG_MEMBERSHIP_URL = "https://api.github.com/orgs/{org}/members/{username}"


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


async def check_org_membership(access_token: str, username: str) -> bool:
    """
    Check if a user is a member of the configured GitHub organization.

    Args:
        access_token: GitHub OAuth access token
        username: GitHub username to check (unused in new implementation but kept for compatibility)

    Returns:
        True if user is a member, False otherwise
    """

    try:
        # Use the user-centric membership endpoint which is more reliable for checking
        # if the authenticated user is a member, even if membership is private.
        # Requires 'read:org' scope.
        org = settings.GITHUB_ORGANIZATION
        url = f"https://api.github.com/user/memberships/orgs/{org}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 200:
                data = response.json()
                # Check if state is active (not pending)
                return data.get("state") == "active"

            return False
    except HTTPException:
        raise
    except Exception:
        return False


async def sync_user_github_repos(access_token: str, max_repos: int = 100) -> list[str]:
    """
    Fetch list of repos the user has access to on GitHub.

    Args:
        access_token: GitHub OAuth access token
        max_repos: Maximum number of repos to fetch (default 100)

    Returns:
        List of repo full_names (e.g., ["owner/repo1", "owner/repo2"])
    """
    repos = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Fetch repos explicitly from the configured organization
            # usage of /orgs/{org}/repos ensures we only get repos for that org
            # and avoids pagination issues where personal repos might crowd out org repos
            org_name = settings.GITHUB_ORGANIZATION
            response = await client.get(
                f"https://api.github.com/orgs/{org_name}/repos",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "per_page": min(max_repos, 100),
                    "sort": "updated",
                    "type": "all",  # all repos (public, private, member)
                },
            )
            if response.status_code == 200:
                data = response.json()
                repos = [repo.get("full_name") for repo in data if repo.get("full_name")]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync GitHub repositories: {str(e)}",
        )

    return repos


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
        "state": state,
        "redirect_url": redirect_url,
        "created_at": datetime.now(timezone.utc),
        "used": False,
        "used_at": None,
    }
    db.github_states.insert_one(document)
    return document


async def exchange_code_for_token(
    db: Database, code: str, state: str
) -> Tuple[OAuthIdentity, Optional[str]]:
    _require_github_credentials()

    oauth_state = db.github_states.find_one({"state": state, "used": False})
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
        error_details = (
            token_data.get("error_description") or token_data.get("error") or str(token_data)
        )
        print(f"GitHub OAuth Error: {error_details}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub did not return an access token. Error: {error_details}",
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
            primary = next((item.get("email") for item in emails if item.get("primary")), None)
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

    # Check organization membership
    github_login = user_data.get("login")
    is_org_member = await check_org_membership(access_token, github_login)

    # If not org member, deny access
    if not is_org_member:
        org_name = settings.GITHUB_ORGANIZATION
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You must be a member of the '{org_name}' organization to use this application.",
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

    # Sync user's GitHub repo access for RBAC
    # This caches which repos the user can access on GitHub
    accessible_repos = await sync_user_github_repos(access_token)
    if accessible_repos:
        db.users.update_one(
            {"_id": user_doc.id},
            {
                "$set": {
                    "github_accessible_repos": accessible_repos,
                    "github_repos_synced_at": datetime.now(timezone.utc),
                }
            },
        )

    db.github_states.update_one(
        {"state": state},
        {"$set": {"used": True, "used_at": datetime.now(timezone.utc)}},
    )

    redirect_url = oauth_state.get("redirect_url")
    # Return identity doc (used in other handlers) and optional redirect path
    return identity_doc, redirect_url
