from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.entities.base import BaseEntity, PyObjectId


class ScanJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ScanJob(BaseEntity):
    repo_id: PyObjectId = Field(...)
    build_id: PyObjectId = Field(...)
    commit_sha: str = Field(...)
    status: ScanJobStatus = Field(default=ScanJobStatus.PENDING)

    # Execution details
    worker_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # Results
    sonar_component_key: Optional[str] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None  # Could be a link to log file or short snippet

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}
