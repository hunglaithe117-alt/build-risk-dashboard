"""GitHub Token management API endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, Path, status, Body

from app.middleware.auth import get_current_user
from app.dtos.token import (
    TokenCreateRequest,
    TokenUpdateRequest,
    TokenResponse,
    TokenPoolStatusResponse,
    TokenVerifyResponse,
    TokenListResponse,
    RefreshAllResponse,
)
from app.services.token_service import TokenService


router = APIRouter(prefix="/tokens", tags=["GitHub Tokens"])


def get_token_service() -> TokenService:
    """Get token service instance."""
    return TokenService()


@router.post("/refresh-all", response_model=RefreshAllResponse)
async def refresh_all_tokens(
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """
    Refresh rate limit info for all tokens by querying GitHub API.

    Uses tokens from GITHUB_TOKENS env var stored in Redis pool.
    """
    result = await service.refresh_all_tokens()
    return RefreshAllResponse(**result)


@router.get("/", response_model=TokenListResponse)
async def list_tokens(
    include_disabled: bool = False,
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """List all GitHub tokens (masked, without actual token values)."""
    result = service.list_tokens(include_disabled=include_disabled)
    return TokenListResponse(
        items=[TokenResponse(**t) for t in result["items"]],
        total=result["total"],
    )


@router.get("/status", response_model=TokenPoolStatusResponse)
async def get_pool_status(
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """Get overall status of the token pool."""
    status_data = service.get_pool_status()
    return TokenPoolStatusResponse(**status_data)


@router.post("/", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    request: TokenCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """
    Add a new GitHub token to the pool.

    The token will be hashed for secure storage - we never store the plaintext.
    """
    token_info = service.create_token(
        token=request.token,
        label=request.label or "",
    )
    return TokenResponse(**token_info)


@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: str = Path(..., description="Token ID"),
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """Get details of a specific token."""
    token_info = service.get_token(token_id)
    return TokenResponse(**token_info)


@router.patch("/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: str = Path(..., description="Token ID"),
    request: TokenUpdateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """Update a token's label or status."""
    token_info = service.update_token(
        token_id=token_id,
        label=request.label,
        token_status=request.status,
    )
    return TokenResponse(**token_info)


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: str = Path(..., description="Token ID"),
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """Remove a token from the pool."""
    service.delete_token(token_id)
    return None


@router.post("/{token_id}/verify", response_model=TokenVerifyResponse)
async def verify_token(
    token_id: str = Path(..., description="Token ID"),
    raw_token: Optional[str] = Body(
        None, embed=True, description="Raw token for verification"
    ),
    current_user: dict = Depends(get_current_user),
    service: TokenService = Depends(get_token_service),
):
    """
    Verify a token is still valid by calling GitHub API.

    Note: For security, we don't store raw tokens. To verify, you must provide
    the raw token value. This is typically used right after adding a new token.
    """
    result = await service.verify_token(token_id, raw_token)
    return TokenVerifyResponse(**result)
