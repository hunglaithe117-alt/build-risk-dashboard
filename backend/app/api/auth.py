from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.config import settings
from app.database.mongo import get_db
from app.dtos import (
    GithubOAuthInitRequest,
    GithubAuthorizeResponse,
    AuthVerifyResponse,
)
from app.services.github.github_oauth import (
    build_authorize_url,
    create_oauth_state,
    exchange_code_for_token,
)
from app.services.auth import create_access_token
from app.middleware.auth import get_current_user
from app.services.github.github_token_manager import (
    check_github_token_status,
    GitHubTokenStatus,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/github/login", response_model=GithubAuthorizeResponse)
def initiate_github_login(
    payload: GithubOAuthInitRequest | None = Body(default=None),
    db: Database = Depends(get_db),
):
    """Initiate GitHub OAuth flow by creating a state token."""
    payload = payload or GithubOAuthInitRequest()
    oauth_state = create_oauth_state(db, redirect_url=payload.redirect_path)
    authorize_url = build_authorize_url(oauth_state["_id"])
    return {"authorize_url": authorize_url, "state": oauth_state["_id"]}


@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(..., description="GitHub authorization code"),
    state: str = Query(..., description="GitHub OAuth state token"),
    db: Database = Depends(get_db),
):
    """Handle GitHub OAuth callback, exchange code for token, and redirect to frontend."""
    identity_doc, redirect_path = await exchange_code_for_token(
        db, code=code, state=state
    )
    user_id = identity_doc.get("user_id")

    # Create JWT access token with expiration matching configuration
    jwt_token = create_access_token(subject=user_id)

    redirect_target = settings.FRONTEND_BASE_URL.rstrip("/")
    if redirect_path:
        redirect_target = f"{redirect_target}{redirect_path}"
    else:
        redirect_target = f"{redirect_target}/integrations/github?status=success"

    response = RedirectResponse(url=redirect_target)

    # Set cookie for frontend usage
    # Cookie expires when JWT expires
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=not settings.DEBUG,  # Use secure cookies in production
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    # Append token to query string in debug mode for convenience
    if settings.DEBUG and "token=" not in redirect_target:
        sep = "?" if "?" not in redirect_target else "&"
        response.headers["location"] = f"{redirect_target}{sep}token={jwt_token}"

    return response


@router.post("/github/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_github_token(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Remove stored GitHub access tokens for the current user."""
    user_id = user["_id"]

    result = db.oauth_identities.update_many(
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


@router.post("/refresh")
async def refresh_access_token(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Refresh the JWT access token for the current user.

    This generates a new JWT token for the application (not GitHub token).
    The new token will have a fresh expiration time.
    """
    user_id = user["_id"]
    new_token = create_access_token(subject=user_id)

    return {
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me")
async def get_current_user_info(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Get current authenticated user information."""
    user_id = user["_id"]

    # Get GitHub identity if exists
    identity = db.oauth_identities.find_one({"user_id": user_id, "provider": "github"})

    response = {
        "id": str(user["_id"]),
        "email": user.get("email"),
        "name": user.get("name"),
        "role": user.get("role", "user"),
        "created_at": (
            user.get("created_at").isoformat() if user.get("created_at") else None
        ),
    }

    if identity:
        token_status, _ = await check_github_token_status(
            db, user_id, verify_with_api=False
        )
        response["github"] = {
            "connected": token_status == GitHubTokenStatus.VALID,
            "login": identity.get("account_login"),
            "name": identity.get("account_name"),
            "avatar_url": identity.get("account_avatar_url"),
            "token_status": token_status,
        }
    else:
        response["github"] = {"connected": False}

    return response


@router.get("/verify", response_model=AuthVerifyResponse)
async def verify_auth_status(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Verify if the current user has a valid GitHub access token.

    Checks:
    1. JWT token validity (handled by get_current_user dependency)
    2. GitHub OAuth identity exists
    3. GitHub token exists and not expired
    4. Optionally verifies token with GitHub API
    """
    user_id = user["_id"]

    # Check GitHub token status
    token_status, identity = await check_github_token_status(
        db, user_id, verify_with_api=True
    )

    if token_status == GitHubTokenStatus.MISSING:
        return {
            "authenticated": True,
            "github_connected": False,
            "reason": "no_github_identity",
            "user": {
                "id": str(user["_id"]),
                "email": user.get("email"),
                "name": user.get("name"),
            },
        }

    if token_status == GitHubTokenStatus.EXPIRED:
        return {
            "authenticated": True,
            "github_connected": False,
            "reason": "github_token_expired",
            "user": {
                "id": str(user["_id"]),
                "email": user.get("email"),
                "name": user.get("name"),
            },
            "github": {
                "login": identity.get("account_login"),
                "name": identity.get("account_name"),
                "avatar_url": identity.get("account_avatar_url"),
            },
        }

    if token_status == GitHubTokenStatus.REVOKED:
        return {
            "authenticated": True,
            "github_connected": False,
            "reason": "github_token_revoked",
            "user": {
                "id": str(user["_id"]),
                "email": user.get("email"),
                "name": user.get("name"),
            },
            "github": {
                "login": identity.get("account_login"),
                "name": identity.get("account_name"),
                "avatar_url": identity.get("account_avatar_url"),
            },
        }

    # Token is valid
    return {
        "authenticated": True,
        "github_connected": True,
        "user": {
            "id": str(user["_id"]),
            "email": user.get("email"),
            "name": user.get("name"),
        },
        "github": {
            "login": identity.get("account_login"),
            "name": identity.get("account_name"),
            "avatar_url": identity.get("account_avatar_url"),
            "scopes": identity.get("scopes"),
        },
    }
