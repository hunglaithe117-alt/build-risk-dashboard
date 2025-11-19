"""Pipeline and queue DTOs"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PipelineStage(BaseModel):
    key: str
    label: str
    status: Literal["pending", "running", "completed", "blocked"]
    percent_complete: int = Field(..., ge=0, le=100)
    duration_seconds: Optional[int] = None
    items_processed: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    issues: List[str] = Field(default_factory=list)


class PipelineStatusResponse(BaseModel):
    last_run: datetime
    next_run: datetime
    normalized_features: int
    pending_repositories: int
    anomalies_detected: int
    stages: List[PipelineStage]


class QueueHealthResponse(BaseModel):
    last_heartbeat: datetime
    repositories_scheduled: int
