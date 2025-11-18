"""Import job entity - tracks repository import progress"""

from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class ImportJob(BaseModel):
    """Import job entity stored in MongoDB"""

    id: Optional[str] = Field(None, alias="_id")
    repository: str
    branch: str
    user_id: Optional[str] = None
    installation_id: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed", "waiting_webhook", "queued"]
    progress: int = Field(0, ge=0, le=100)
    builds_imported: int = 0
    commits_analyzed: int = 0
    tests_collected: int = 0
    initiated_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
