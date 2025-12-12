from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from app.entities.base import BaseEntity


class GitHubTokenStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    RATE_LIMITED = "rate_limited"
    INVALID = "invalid"


class GithubToken(BaseEntity):
    token_hash: str = Field(..., description="SHA-256 hash of the token for lookup")
    masked_token: str = Field(
        ..., description="Masked token showing last 4 chars (e.g., ****abc1)"
    )

    label: str = Field(default="", description="User-defined label for this token")

    status: GitHubTokenStatus = GitHubTokenStatus.ACTIVE

    rate_limit_remaining: Optional[int] = Field(
        default=None, description="Remaining API requests for this token"
    )
    rate_limit_limit: Optional[int] = Field(
        default=None, description="Total rate limit for this token (usually 5000)"
    )
    rate_limit_reset_at: Optional[datetime] = Field(
        default=None, description="When the rate limit resets"
    )

    last_used_at: Optional[datetime] = Field(
        default=None, description="Last time this token was used for an API call"
    )
    total_requests: int = Field(
        default=0, description="Total number of requests made with this token"
    )

    last_validated_at: Optional[datetime] = Field(
        default=None,
        description="Last time this token was validated against GitHub API",
    )
    validation_error: Optional[str] = Field(
        default=None, description="Error message from last validation attempt"
    )

    class Config:
        collection = "github_tokens"
        use_enum_values = True
