from enum import Enum
from typing import Dict

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


class ModelBuild(BaseEntity):
    repo_id: PyObjectId
    workflow_run_id: int
    head_sha: str | None = None  # Commit SHA for previous build lookup

    status: str = BuildStatus.SUCCESS.value
    extraction_status: str = ExtractionStatus.PENDING.value
    error_message: str | None = None
    is_missing_commit: bool = False

    features: Dict = {}

    class Config:
        collection = "model_builds"
