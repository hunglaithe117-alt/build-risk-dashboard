from datetime import datetime
from enum import Enum
from typing import Optional

from .base import BaseEntity, PyObjectId


class DatasetBuildStatus(str, Enum):
    PENDING = "pending"
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"


class DatasetBuild(BaseEntity):
    # Dataset reference
    dataset_id: PyObjectId

    # From CSV
    build_id_from_csv: str
    repo_name_from_csv: str

    # Validation status
    status: DatasetBuildStatus = DatasetBuildStatus.PENDING
    validation_error: Optional[str] = None
    validated_at: Optional[datetime] = None

    repo_id: Optional[PyObjectId] = None
    workflow_run_id: Optional[PyObjectId] = None

    class Config:
        collection = "dataset_builds"
