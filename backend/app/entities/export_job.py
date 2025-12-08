"""
Export Job Entity - Tracks export job status and metadata.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from .base import BaseEntity, PyObjectId


class ExportFormat(str, Enum):
    """Supported export formats."""

    CSV = "csv"
    JSON = "json"


class ExportStatus(str, Enum):
    """Export job status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportJob(BaseEntity):
    """
    Represents an export job for background processing.

    Used when the dataset is too large for streaming response.
    """

    repo_id: PyObjectId
    user_id: PyObjectId
    format: str = ExportFormat.CSV.value
    status: str = ExportStatus.PENDING.value

    # Filters
    features: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    build_status: Optional[str] = None

    # Progress tracking
    total_rows: int = 0
    processed_rows: int = 0

    # Result
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
