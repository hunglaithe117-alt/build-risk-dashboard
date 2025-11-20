from fastapi import (
    APIRouter,
    Body,
    Depends,
    Query,
    status,
    Cookie,
    HTTPException,
    Response,
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


@router.post("/github/login", response_model=GithubAuthorizeResponse)
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
    service = AuthService(db)
    jwt_token, refresh_token, redirect_path = await service.handle_github_callback(
        code, state
    )

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
    service = AuthService(db)
    service.revoke_github_token(user["_id"])


@router.post("/refresh", response_model=TokenResponse)
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


@router.get("/me", response_model=UserDetailResponse)
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
