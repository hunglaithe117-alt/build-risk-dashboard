from datetime import datetime
from enum import Enum
from typing import List, Optional

from .base import BaseEntity, PyObjectId


class BuildStatus(str, Enum):
    """
    GitHub Actions workflow run conclusion.
    Since we only import completed runs, this represents the final outcome.
    See: https://docs.github.com/en/rest/actions/workflow-runs
    """

    # Success
    SUCCESS = "success"

    # Failure
    FAILURE = "failure"

    # Cancelled by user
    CANCELLED = "cancelled"

    # Skipped (e.g., path filters, conditional)
    SKIPPED = "skipped"

    # Timed out
    TIMED_OUT = "timed_out"

    # Neutral (neither success nor failure)
    NEUTRAL = "neutral"


class ExtractionStatus(str, Enum):
    """Feature extraction pipeline status."""

    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"  # Some features extracted but not all (e.g., missing commit)
    FAILED = "failed"


class BuildSample(BaseEntity):
    repo_id: PyObjectId
    workflow_run_id: int
    status: str
    extraction_status: str = ExtractionStatus.PENDING.value  # Feature extraction status
    error_message: str | None = None
    is_missing_commit: bool = False

    features: dict = {}

    sonar_scan_status: str | None = None

    class Config:
        populate_by_name = True
