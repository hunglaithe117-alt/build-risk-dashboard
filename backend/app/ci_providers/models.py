from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CIProvider(str, Enum):
    """Supported CI/CD providers."""

    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    JENKINS = "jenkins"
    CIRCLECI = "circleci"
    TRAVIS_CI = "travis_ci"


class BuildStatus(str, Enum):
    """Normalized build status across all providers."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class BuildData(BaseModel):
    """Normalized build data from any CI provider."""

    # Identifiers
    build_id: str = Field(..., description="Unique build identifier from CI")
    build_number: Optional[int] = Field(
        None, description="Sequential build number if available"
    )

    # Repository info
    repo_name: str = Field(..., description="Full repository name (owner/repo)")
    branch: Optional[str] = None

    # Commit info
    commit_sha: Optional[str] = None
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None

    # Status
    status: BuildStatus = BuildStatus.UNKNOWN
    conclusion: Optional[str] = None  # Provider-specific conclusion

    # Timing
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # URLs
    web_url: Optional[str] = None
    logs_url: Optional[str] = None

    logs_available: Optional[bool] = None
    is_bot_commit: Optional[bool] = None

    # Provider metadata
    provider: CIProvider
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class JobData(BaseModel):
    """Normalized job/step data within a build."""

    job_id: str
    job_name: str
    status: BuildStatus = BuildStatus.UNKNOWN
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Log content if available
    log_content: Optional[str] = None
    log_url: Optional[str] = None


class LogFile(BaseModel):
    """Log file from a CI build."""

    job_id: str
    job_name: str
    path: str
    content: str
    size_bytes: int = 0


class ProviderConfig(BaseModel):
    """Configuration for a CI provider connection."""

    provider: CIProvider
    base_url: Optional[str] = None  # API base URL
    token: Optional[str] = None  # Auth token
    username: Optional[str] = None
    password: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)
