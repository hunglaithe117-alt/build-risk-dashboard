"""
Dataset Scan Entity

Tracks a scanning job for a dataset using integration tools.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId


class DatasetScanStatus(str, Enum):
    """Status of a dataset scan job."""

    PENDING = "pending"  # Created, not yet started
    RUNNING = "running"  # Scan in progress
    COMPLETED = "completed"  # All commits scanned successfully
    PARTIAL = "partial"  # Some commits scanned, some pending (async)
    FAILED = "failed"  # Scan failed
    CANCELLED = "cancelled"  # Cancelled by user


class DatasetScan(BaseEntity):
    """
    Tracks a scan job for a dataset.

    A scan job orchestrates scanning multiple commits from a dataset
    using a specific integration tool (SonarQube or Trivy).
    """

    class Config:
        collection = "dataset_scans"

    dataset_id: PyObjectId
    user_id: PyObjectId
    tool_type: str  # "sonarqube" or "trivy"

    # Commits to scan (unique commits from dataset)
    # Each: {"sha": "abc123", "repo_full_name": "owner/repo", "row_indices": [0, 5, 10]}
    commits: List[Dict[str, Any]] = Field(default_factory=list)

    # Scope selection
    # None = all commits, otherwise list of specific SHA values to scan
    selected_commit_shas: Optional[List[str]] = None

    # Progress tracking
    status: DatasetScanStatus = DatasetScanStatus.PENDING
    total_commits: int = 0
    scanned_commits: int = 0
    failed_commits: int = 0
    pending_commits: int = 0  # For async tools (SonarQube) waiting for webhook

    # Error info (if failed)
    error_message: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Aggregated results summary
    results_summary: Optional[Dict[str, Any]] = None

    # Celery task tracking
    task_id: Optional[str] = None

    def mark_started(self):
        """Mark scan as started."""
        self.status = DatasetScanStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, results_summary: Optional[Dict[str, Any]] = None):
        """Mark scan as completed."""
        self.status = DatasetScanStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        if results_summary:
            self.results_summary = results_summary

    def mark_partial(self, pending_count: int):
        """Mark scan as partial (waiting for async results)."""
        self.status = DatasetScanStatus.PARTIAL
        self.pending_commits = pending_count

    def mark_failed(self, error: str):
        """Mark scan as failed."""
        self.status = DatasetScanStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)

    def mark_cancelled(self):
        """Mark scan as cancelled."""
        self.status = DatasetScanStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)

    def update_progress(self, scanned: int = 0, failed: int = 0, pending: int = 0):
        """Update progress counters."""
        self.scanned_commits = scanned
        self.failed_commits = failed
        self.pending_commits = pending

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_commits == 0:
            return 0.0
        completed = self.scanned_commits + self.failed_commits
        return (completed / self.total_commits) * 100
