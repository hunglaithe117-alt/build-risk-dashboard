"""
RawBuildRun Entity - Immutable CI/CD build run data from any provider.

This entity stores raw build run information fetched from multiple CI providers (GitHub Actions, CircleCI, etc.).
It serves as the single source of truth for build/CI run data across all providers.

Key design principles:
- Immutable: Raw data from CI providers, should not be modified
- Provider-agnostic: Supports multiple CI/CD providers
- Shared: Multiple flows can process the same build run
- Complete: Contains normalized and raw provider metadata
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import Field

from app.ci_providers.models import BuildConclusion, BuildStatus, CIProvider
from app.entities.base import BaseEntity, PyObjectId


class RawBuildRun(BaseEntity):
    """
    Raw build run data from any CI/CD provider.

    This represents a single normalized CI/CD run (build) from any supported provider
    (GitHub Actions, CircleCI, Travis CI, etc.).
    Multiple flows can reference and process this data.
    """

    class Config:
        collection = "raw_build_runs"

    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )

    ci_run_id: str = Field(
        ...,
        description="Unique workflow run ID from CI provider (GitHub Actions run ID, CircleCI build ID, etc.)",
    )

    build_number: Optional[int] = Field(
        None,
        description="Sequential build number if available from provider",
    )

    repo_name: str = Field(
        default="",
        description="Full repository name (owner/repo)",
    )

    branch: str = Field(
        default="",
        description="Branch name",
    )

    # Commit info
    commit_sha: str = Field(
        default="",
        description="Git commit SHA that triggered this run",
    )

    commit_message: Optional[str] = Field(
        None,
        description="Commit message",
    )

    commit_author: Optional[str] = Field(
        None,
        description="Commit author name/email",
    )

    # Effective SHA (for fork commits that need replay)
    effective_sha: Optional[str] = Field(
        None,
        description="Effective commit SHA for local git operations. "
        "Set when original commit is replayed (fork commits). "
        "If None, use commit_sha.",
    )

    # Status and Conclusion (separate concepts)
    status: BuildStatus = Field(
        default=BuildStatus.UNKNOWN,
        description="Current state: pending/queued/running/completed/unknown",
    )

    conclusion: BuildConclusion = Field(
        default=BuildConclusion.NONE,
        description="Final result when completed: success/failure/cancelled/skipped/timed_out/action_required/neutral/unknown",
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        default=None,
        description="When the build was created",
    )

    started_at: Optional[datetime] = Field(
        default=None,
        description="When the build started running",
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        description="When the build completed",
    )

    # Duration
    duration_seconds: Optional[float] = Field(
        None,
        description="Total duration in seconds",
    )

    # URLs
    web_url: Optional[str] = Field(
        None,
        description="URL to view the build in CI provider UI",
    )

    # Log storage
    logs_available: Optional[bool] = Field(
        default=None,
        description="Whether logs have been downloaded and stored",
    )

    logs_path: Optional[str] = Field(
        None,
        description="Path to stored log files (if downloaded)",
    )

    logs_expired: bool = Field(
        default=False,
        description="Whether logs have expired and are no longer available from CI provider",
    )

    # CI Provider information
    provider: CIProvider = Field(
        ...,
        description="CI/CD provider type",
    )

    # Full provider metadata
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete raw API response from CI provider",
    )

    is_bot_commit: Optional[bool] = Field(
        None,
        description="Whether this build was triggered by a bot (Dependabot, etc.)",
    )
