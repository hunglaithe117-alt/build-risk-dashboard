"""
RawWorkflowRun Entity - Immutable GitHub Actions workflow run data.

This entity stores raw workflow run information fetched from GitHub Actions.
It serves as the single source of truth for build/CI run data.

Key design principles:
- Immutable: Raw data from GitHub, should not be modified
- Shared: Multiple flows can process the same workflow run
- Complete: Contains all relevant GitHub Actions metadata
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId


class RawWorkflowRun(BaseEntity):
    """
    Raw workflow run data from GitHub Actions.

    This represents a single CI/CD run (build) from GitHub Actions.
    Multiple flows can reference and process this data.
    """

    class Config:
        collection = "raw_workflow_runs"

    # Reference to repository
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )

    # Core identifiers
    workflow_run_id: int = Field(
        ...,
        description="GitHub Actions workflow run ID. Unique within a repository.",
    )

    # Build information
    build_number: int = Field(
        ...,
        description="Sequential build number (run_number from GitHub)",
    )

    # Git information
    head_sha: str = Field(
        ...,
        description="Git commit SHA that triggered this run",
    )
    head_branch: Optional[str] = Field(
        None,
        description="Branch name",
    )

    # Status and conclusion
    status: str = Field(
        ...,
        description="Run status: queued, in_progress, completed",
    )
    conclusion: str = Field(
        ...,
        description="Run conclusion: success, failure, cancelled, skipped, timed_out, action_required, neutral",
    )

    # Timestamps
    build_created_at: datetime = Field(
        ...,
        description="When the workflow run was created",
    )
    build_updated_at: datetime = Field(
        ...,
        description="Last update time",
    )

    # Duration
    duration_seconds: float = Field(
        ...,
        description="Total duration in seconds",
    )

    # Jobs information
    jobs_count: int = Field(
        default=0,
        description="Number of jobs in this run",
    )
    jobs_metadata: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of jobs with their status/conclusion",
    )

    # Full GitHub metadata
    github_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete GitHub API response for this workflow run",
    )

    # Log storage
    has_logs: bool = Field(
        default=False,
        description="Whether we have downloaded and stored the logs",
    )
    logs_path: Optional[str] = Field(
        None,
        description="Path to stored log files (if downloaded)",
    )
