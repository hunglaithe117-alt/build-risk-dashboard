from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from app.entities.base import PyObjectId


class BuildSummary(BaseModel):
    id: str = Field(..., alias="_id")
    build_number: int
    build_conclusion: str  # GitHub workflow conclusion: "success", "failure", etc.
    extraction_status: (
        str  # Feature extraction process status: "pending", "completed", "failed"
    )
    commit_sha: str
    created_at: Optional[datetime] = None
    duration: Optional[float] = None
    num_jobs: Optional[int] = None
    num_tests: Optional[int] = None
    error_message: Optional[str] = None
    is_missing_commit: bool = False

    # Workflow info
    workflow_run_id: int

    # Logs fields
    logs_available: Optional[bool] = None
    logs_expired: Optional[bool] = None

    class Config:
        populate_by_name = True


class BuildDetail(BuildSummary):
    features: dict = {}

    # Logs
    error_message: Optional[str] = None


class BuildListResponse(BaseModel):
    items: List[BuildSummary]
    total: int
    page: int
    size: int
