from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.entities.base import BaseEntity, PyObjectId


class ScanErrorType(str, Enum):
    SCAN_ERROR = "scan_error"
    CONFIG_ERROR = "config_error"


class ScanStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RESOLVED = "resolved"


class FailedScan(BaseEntity):
    """Tracks scans that failed permanently and may need configuration fixes."""

    repo_id: PyObjectId = Field(...)
    build_id: PyObjectId = Field(...)
    job_id: PyObjectId = Field(...)  # Reference to the failed ScanJob
    commit_sha: str = Field(...)

    # Error details
    reason: str = Field(...)  # Error message
    error_type: ScanErrorType = Field(default=ScanErrorType.SCAN_ERROR)

    # Status tracking
    status: ScanStatus = Field(default=ScanStatus.PENDING)

    # Config override for retry
    config_override: Optional[str] = None  # Custom sonar-project.properties content
    config_source: Optional[str] = None  # Source of the config (e.g., "text", "file")

    # Retry tracking
    retry_count: int = Field(default=0)
    resolved_at: Optional[datetime] = None

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}
