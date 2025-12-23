"""DTOs for GitHub Token management API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TokenCreateRequest(BaseModel):
    """Request to add a new GitHub token."""

    token: str = Field(..., description="GitHub personal access token")
    label: Optional[str] = Field(default=None, description="User-friendly label")


class TokenUpdateRequest(BaseModel):
    """Request to update a token's properties."""

    label: Optional[str] = Field(default=None, description="Updated label")
    status: Optional[str] = Field(
        default=None, description="Updated status (active or disabled only)"
    )


class TokenResponse(BaseModel):
    """Token info response (masked, no raw token)."""

    id: str
    masked_token: str
    label: str
    status: str
    rate_limit_remaining: Optional[int] = None
    rate_limit_limit: Optional[int] = None
    rate_limit_reset_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    total_requests: int = 0
    created_at: Optional[datetime] = None
    last_validated_at: Optional[datetime] = None
    validation_error: Optional[str] = None


class TokenPoolStatusResponse(BaseModel):
    """Overall token pool status."""

    total_tokens: int
    active_tokens: int
    rate_limited_tokens: int
    invalid_tokens: int
    disabled_tokens: int
    estimated_requests_available: int
    next_reset_at: Optional[str] = None
    pool_healthy: bool


class TokenVerifyResponse(BaseModel):
    """Response from token verification."""

    valid: bool
    error: Optional[str] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_limit: Optional[int] = None


class TokenListResponse(BaseModel):
    """Response with list of tokens."""

    items: List[TokenResponse]
    total: int


class RefreshAllResponse(BaseModel):
    """Response for refresh all tokens."""

    refreshed: int
    failed: int
    results: List[dict]
