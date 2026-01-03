from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException, status
from jose import JWTError, jwt
from pymongo.database import Database

from app.config import settings
from app.dtos.auth import (
    AuthVerifyResponse,
    GitHubInfo,
    TokenResponse,
    UserDetailResponse,
)
from app.dtos.github import GithubAuthorizeResponse, GithubOAuthInitRequest
from app.services.github.github_oauth import (
    build_authorize_url,
    create_oauth_state,
    exchange_code_for_token,
)
from app.services.github.github_token_manager import (
    GitHubTokenStatus,
    check_github_token_status,
)
from app.utils.datetime import utc_now


class AuthService:
    def __init__(self, db: Database):
        self.db = db

    def initiate_github_login(
        self, payload: GithubOAuthInitRequest
    ) -> GithubAuthorizeResponse:
        """Initiate GitHub OAuth flow by creating a state token."""
        oauth_state = create_oauth_state(self.db, redirect_url=payload.redirect_path)
        authorize_url = build_authorize_url(oauth_state["state"])
        return GithubAuthorizeResponse(
            authorize_url=authorize_url, state=oauth_state["state"]
        )

    async def handle_github_callback(
        self, code: str, state: str
    ) -> Tuple[str, str, str]:
        """
        Handle GitHub OAuth callback, exchange code for token.
        Returns (access_token, refresh_token, redirect_path).
        """
        identity_doc, redirect_path = await exchange_code_for_token(
            self.db, code=code, state=state
        )
        user_id = identity_doc.user_id

        # Create JWT access token with expiration matching configuration
        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)

        return access_token, refresh_token, redirect_path

    def revoke_github_token(self, user_id: str) -> None:
        """Remove stored GitHub access tokens for the current user."""
        result = self.db.oauth_identities.update_many(
            {"user_id": user_id, "provider": "github"},
            {
                "$set": {
                    "token_status": "revoked",
                    "token_invalid_reason": "user_revoked",
                    "token_invalidated_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
                "$unset": {
                    "access_token": "",
                    "refresh_token": "",
                },
            },
        )
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No GitHub identities found to revoke.",
            )

    def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Refresh the JWT access token using a valid refresh token."""
        try:
            payload = decode_refresh_token(refresh_token)
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token",
                )

            # Check if user exists
            user = self.db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )

            new_access_token = create_access_token(subject=user_id)

            return TokenResponse(
                access_token=new_access_token,
                token_type="bearer",
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not refresh token: {str(e)}",
            )

    async def get_current_user_info(self, user: dict) -> UserDetailResponse:
        """Get current authenticated user information."""
        user_id = user["_id"]

        # Get GitHub identity if exists
        identity = self.db.oauth_identities.find_one(
            {"user_id": user_id, "provider": "github"}
        )

        github_info = GitHubInfo(connected=False)

        if identity:
            token_status, _ = await check_github_token_status(
                self.db, user_id, verify_with_api=False
            )
            github_info = GitHubInfo(
                connected=token_status == GitHubTokenStatus.VALID,
                login=identity.get("account_login"),
                name=identity.get("account_name"),
                avatar_url=identity.get("account_avatar_url"),
                token_status=token_status,
            )

        return UserDetailResponse(
            id=str(user["_id"]),
            email=user.get("email"),
            name=user.get("name"),
            role=user.get("role", "user"),
            created_at=(
                user.get("created_at").isoformat() if user.get("created_at") else None
            ),
            github=github_info,
        )

    async def verify_auth_status(self, user: dict) -> AuthVerifyResponse:
        """Verify if the current user has a valid GitHub access token."""
        user_id = user["_id"]

        # Check GitHub token status
        token_status, identity = await check_github_token_status(
            self.db, user_id, verify_with_api=True
        )

        user_info = {
            "id": str(user["_id"]),
            "email": user.get("email"),
            "name": user.get("name"),
            "role": user.get("role", "user"),
            "github_accessible_repos": user.get("github_accessible_repos", []),
        }

        github_data = None
        if identity:
            github_data = {
                "login": identity.get("account_login"),
                "name": identity.get("account_name"),
                "avatar_url": identity.get("account_avatar_url"),
            }

        if token_status == GitHubTokenStatus.MISSING:
            return AuthVerifyResponse(
                authenticated=True,
                github_connected=False,
                reason="no_github_identity",
                user=user_info,
            )

        if token_status == GitHubTokenStatus.EXPIRED:
            return AuthVerifyResponse(
                authenticated=True,
                github_connected=False,
                reason="github_token_expired",
                user=user_info,
                github=github_data,
            )

        if token_status == GitHubTokenStatus.REVOKED:
            return AuthVerifyResponse(
                authenticated=True,
                github_connected=False,
                reason="github_token_revoked",
                user=user_info,
                github=github_data,
            )

        # Token is valid
        if identity:
            github_data["scopes"] = identity.get("scopes")

        return AuthVerifyResponse(
            authenticated=True,
            github_connected=True,
            user=user_info,
            github=github_data,
        )


def create_access_token(
    subject: str | int, expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = utc_now() + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": utc_now(),
        "type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token


def create_refresh_token(
    subject: str | int, expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    expire = utc_now() + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": utc_now(),
        "type": "refresh",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        # Validate token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
            )

        # Check if token has expired
        exp = payload.get("exp")
        if exp and utc_now() > datetime.fromtimestamp(exp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        )


def decode_refresh_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        # Validate token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
            )

        # Check if token has expired
        exp = payload.get("exp")
        if exp and utc_now() > datetime.fromtimestamp(exp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has expired",
            )

        return payload

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate refresh token: {str(e)}",
        )
