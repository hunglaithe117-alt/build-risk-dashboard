"""
SonarCommitScan Entity - Tracks SonarQube scans per commit in a version.

Used for tracking scan status and retry functionality.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import Field

from .base import BaseEntity, PyObjectId


class SonarScanStatus(str, Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"


class SonarCommitScan(BaseEntity):
    """
    Tracks SonarQube scan status per commit in a dataset version.

    Flow:
    1. dispatch_scan_for_commit creates this with status=pending
    2. start_sonar_scan_for_version_commit updates to scanning
    3. On completion/webhook, updates to completed with metrics
    4. On failure, updates to failed with error_message

    Allows retry functionality with updated config.
    """

    # Version and commit reference
    dataset_version_id: Optional[PyObjectId] = Field(
        None, description="DatasetVersion ID (legacy)"
    )
    scenario_id: Optional[PyObjectId] = Field(
        None, description="TrainingScenario ID (new flow)"
    )
    commit_sha: str = Field(..., description="Git commit SHA")
    repo_full_name: str = Field(..., description="Repository full name (owner/repo)")

    # Raw repository reference - needed to derive worktree path for retry
    raw_repo_id: PyObjectId = Field(
        ...,
        description="RawRepository ID - used to derive worktree path for scan/retry",
    )

    # SonarQube identifiers
    component_key: str = Field(
        ...,
        description="SonarQube project/component key (format: {version_id}_{repo}_{commit})",
    )

    # Scan configuration (for retry with updated config)
    scan_config: Optional[Dict] = Field(
        None,
        description="SonarQube config: projectKey, extraProperties",
    )
    selected_metrics: Optional[List[str]] = Field(
        None,
        description="Selected metrics to filter",
    )

    # Status tracking
    status: SonarScanStatus = SonarScanStatus.PENDING
    error_message: Optional[str] = None

    # Results (populated on completion)
    metrics: Optional[Dict] = None
    builds_affected: int = Field(
        0,
        description="Number of builds backfilled with results",
    )

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Retry tracking
    retry_count: int = 0

    class Config:
        collection = "sonar_commit_scans"
