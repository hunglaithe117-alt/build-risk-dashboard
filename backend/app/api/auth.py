from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.config import settings
from app.database.mongo import get_db
from app.models.schemas import (
    GithubOAuthInitRequest,
    GithubAuthorizeResponse,
    AuthVerifyResponse,
)
from app.services.github_oauth import (
    build_authorize_url,
    create_oauth_state,
    exchange_code_for_token,
    verify_github_token,
)
from app.services.auth import create_access_token

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
    jwt_token = create_access_token(subject=user_id)
    redirect_target = settings.FRONTEND_BASE_URL.rstrip("/")
    if redirect_path:
        redirect_target = f"{redirect_target}{redirect_path}"
    else:
        redirect_target = f"{redirect_target}/integrations/github?status=success"
    response = RedirectResponse(url=redirect_target)
    # Set cookie for frontend usage; allow credentials cross-site
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    # Also append the token to the query string for convenience while debugging
    # (not recommended for production). If there's already a token or params,
    # we skip this step.
    if settings.DEBUG and "token=" not in redirect_target:
        sep = "?" if "?" not in redirect_target else "&"
        response.headers["location"] = f"{redirect_target}{sep}token={jwt_token}"
    return response


@router.post("/github/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_github_token(db: Database = Depends(get_db)):
    """Remove stored GitHub access tokens."""
    result = db.oauth_identities.update_many(
        {"provider": "github"},
        {
            "$unset": {
                "access_token": "",
                "refresh_token": "",
                "token_expires_at": "",
                "scopes": "",
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No GitHub identities found to revoke.",
        )


@router.get("/verify", response_model=AuthVerifyResponse)
async def verify_auth_status(db: Database = Depends(get_db)):
    """Verify if the current user has a valid GitHub access token."""
    # Find the GitHub OAuth identity
    identity = db.oauth_identities.find_one({"provider": "github"})
    
    if not identity:
        return {"authenticated": False, "reason": "no_identity"}
    
    access_token = identity.get("access_token")
    if not access_token:
        return {"authenticated": False, "reason": "no_token"}
    
    # Check if token has expiration and if it's expired
    token_expires_at = identity.get("token_expires_at")
    if token_expires_at:
        if datetime.now(timezone.utc) >= token_expires_at:
            return {"authenticated": False, "reason": "token_expired"}
    
    # Verify token with GitHub API
    is_valid = await verify_github_token(access_token)
    if not is_valid:
        return {"authenticated": False, "reason": "token_invalid"}
    
    # Get user info
    user_doc = db.users.find_one({"_id": identity["user_id"]})
    
    return {
        "authenticated": True,
        "user": {
            "id": str(user_doc["_id"]) if user_doc else None,
            "email": user_doc.get("email") if user_doc else None,
            "name": user_doc.get("name") if user_doc else None,
        },
        "github": {
            "login": identity.get("account_login"),
            "name": identity.get("account_name"),
            "avatar_url": identity.get("account_avatar_url"),
        },
    }
