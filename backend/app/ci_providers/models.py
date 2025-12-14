from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CIProvider(str, Enum):
    """Supported CI/CD providers."""

    GITHUB_ACTIONS = "github_actions"
    JENKINS = "jenkins"
    CIRCLECI = "circleci"
    TRAVIS_CI = "travis_ci"


class BuildStatus(str, Enum):
    """Workflow run status - indicates current state."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class BuildConclusion(str, Enum):
    """Workflow run conclusion - indicates final result when completed."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    NEUTRAL = "neutral"
    STALE = "stale"
    UNKNOWN = "unknown"
    NONE = "none"  # For builds still running


class BuildData(BaseModel):
    """Normalized build data from any CI provider."""

    # Identifiers
    build_id: str = Field(..., description="Unique build identifier from CI")
    build_number: Optional[int] = Field(
        None, description="Sequential build number if available"
    )

    # Repository info
    repo_name: str = Field(..., description="Full repository name (owner/repo)")
    branch: str

    # Commit info
    commit_sha: str
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None

    # Status and Conclusion (separate concepts)
    status: BuildStatus = (
        BuildStatus.UNKNOWN
    )  # Current state: pending/running/completed
    conclusion: BuildConclusion = (
        BuildConclusion.NONE
    )  # Final result: success/failure/etc

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
