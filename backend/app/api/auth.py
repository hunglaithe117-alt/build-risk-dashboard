from fastapi import (
    APIRouter,
    Body,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.config import settings
from app.database.mongo import get_db
from app.dtos.auth import (
    AuthVerifyResponse,
    TokenResponse,
    UserDetailResponse,
)
from app.dtos.github import (
    GithubAuthorizeResponse,
    GithubOAuthInitRequest,
)
from app.middleware.auth import get_current_user
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/github/login",
    response_model=GithubAuthorizeResponse,
    response_model_by_alias=False,
)
def initiate_github_login(
    payload: GithubOAuthInitRequest | None = Body(default=None),
    db: Database = Depends(get_db),
):
    """Initiate GitHub OAuth flow by creating a state token."""
    service = AuthService(db)
    payload = payload or GithubOAuthInitRequest()
    return service.initiate_github_login(payload)


@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(..., description="GitHub authorization code"),
    state: str = Query(..., description="GitHub OAuth state token"),
    db: Database = Depends(get_db),
):
    """Handle GitHub OAuth callback, exchange code for token, and redirect to frontend."""
    from urllib.parse import quote

    service = AuthService(db)

    try:
        jwt_token, refresh_token, redirect_path = await service.handle_github_callback(
            code, state
        )
    except HTTPException as e:
        # Redirect to login page with error details
        redirect_target = settings.FRONTEND_BASE_URL.rstrip("/")
        error_message = quote(e.detail)
        return RedirectResponse(url=f"{redirect_target}/login?error={error_message}")

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

    # Set refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )

    return response


@router.post("/github/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_github_token(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    """Remove stored GitHub access tokens for the current user."""
    service = AuthService(db)
    service.revoke_github_token(user["_id"])


@router.post(
    "/refresh",
    response_model=TokenResponse,
    response_model_by_alias=False,
)
async def refresh_access_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Database = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing"
        )
    service = AuthService(db)
    token_data = service.refresh_access_token(refresh_token)

    # Set access token cookie
    response.set_cookie(
        key="access_token",
        value=token_data.access_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    return token_data


@router.get(
    "/me",
    response_model=UserDetailResponse,
    response_model_by_alias=False,
)
async def get_current_user_info(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    service = AuthService(db)
    return await service.get_current_user_info(user)


@router.get("/verify", response_model=AuthVerifyResponse)
async def verify_auth_status(
    user: dict = Depends(get_current_user), db: Database = Depends(get_db)
):
    service = AuthService(db)
    return await service.verify_auth_status(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    """Logout user by clearing authentication cookies."""
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
    )
    response.delete_cookie(
        key="refresh_token",
        path="/",
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
    )

