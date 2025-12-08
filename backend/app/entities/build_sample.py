from datetime import datetime
from enum import Enum
from typing import List, Optional

from .base import BaseEntity, PyObjectId


class BuildStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    NEUTRAL = "neutral"


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class BuildSample(BaseEntity):
    repo_id: PyObjectId
    workflow_run_id: int
    status: str
    extraction_status: str = ExtractionStatus.PENDING.value
    error_message: str | None = None
    is_missing_commit: bool = False

    features: dict = {}

    sonar_scan_status: str | None = None

    class Config:
        populate_by_name = True
