"""GitHub Token entity model for database storage."""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.entities.base import BaseEntity


class GithubToken(BaseEntity):
    """
    GitHub personal access token stored in MongoDB.

    Tokens are hashed for security - we never store the plaintext token.
    The masked_token field shows only the last 4 characters for identification.
    """

    # Token identification (stored securely)
    token_hash: str = Field(..., description="SHA-256 hash of the token for lookup")
    masked_token: str = Field(
        ..., description="Masked token showing last 4 chars (e.g., ****abc1)"
    )

    # User-friendly label
    label: str = Field(default="", description="User-defined label for this token")

    # Status tracking
    status: str = Field(
        default="active",
        description="Token status: active, rate_limited, invalid, disabled",
    )

    # Rate limit information (updated from GitHub API response headers)
    rate_limit_remaining: Optional[int] = Field(
        default=None, description="Remaining API requests for this token"
    )
    rate_limit_limit: Optional[int] = Field(
        default=None, description="Total rate limit for this token (usually 5000)"
    )
    rate_limit_reset_at: Optional[datetime] = Field(
        default=None, description="When the rate limit resets"
    )

    # Usage statistics
    last_used_at: Optional[datetime] = Field(
        default=None, description="Last time this token was used for an API call"
    )
    total_requests: int = Field(
        default=0, description="Total number of requests made with this token"
    )

    # Validation result
    last_validated_at: Optional[datetime] = Field(
        default=None,
        description="Last time this token was validated against GitHub API",
    )
    validation_error: Optional[str] = Field(
        default=None, description="Error message from last validation attempt"
    )

    class Config:
        collection = "github_tokens"
