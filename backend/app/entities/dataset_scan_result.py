"""
Dataset Scan Result Entity

Stores individual scan results for each commit in a dataset scan.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId


class DatasetScanResult(BaseEntity):
    """
    Individual scan result for a commit within a dataset scan.

    Each result corresponds to scanning a single commit with the tool.
    Multiple dataset rows may map to the same commit (via row_indices).
    """

    class Config:
        collection = "dataset_scan_results"

    scan_id: PyObjectId  # Parent DatasetScan
    dataset_id: PyObjectId  # For quick lookups
    commit_sha: str
    repo_full_name: str

    # Which rows in dataset this commit maps to
    row_indices: List[int] = Field(default_factory=list)

    # Status
    # pending: waiting to be scanned
    # scanning: scan in progress (for async tools)
    # completed: scan done, results available
    # failed: scan failed
    status: str = "pending"

    # For async tools (SonarQube) - component key for webhook matching
    component_key: Optional[str] = None

    # Scan results (metrics from the tool)
    results: Dict[str, Any] = Field(default_factory=dict)

    # Error details if failed
    error_message: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    scan_duration_ms: Optional[int] = None

    def mark_scanning(self, component_key: Optional[str] = None):
        """Mark as currently scanning."""
        self.status = "scanning"
        self.started_at = datetime.now(timezone.utc)
        if component_key:
            self.component_key = component_key

    def mark_completed(
        self, results: Dict[str, Any], duration_ms: Optional[int] = None
    ):
        """Mark as completed with results."""
        self.status = "completed"
        self.results = results
        self.completed_at = datetime.now(timezone.utc)
        if duration_ms:
            self.scan_duration_ms = duration_ms

    def mark_failed(self, error: str):
        """Mark as failed."""
        self.status = "failed"
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)
