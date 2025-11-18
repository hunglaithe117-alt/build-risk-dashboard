"""Workflow entities - GitHub Actions workflow runs and jobs"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class WorkflowRun(BaseModel):
    """Workflow run entity stored in MongoDB"""

    id: int = Field(..., alias="_id")
    repository: str
    workflow_name: Optional[str] = None
    head_branch: Optional[str] = None
    head_sha: Optional[str] = None
    status: Optional[str] = None
    conclusion: Optional[str] = None
    run_number: Optional[int] = None
    event: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    run_started_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class WorkflowJob(BaseModel):
    """Workflow job entity stored in MongoDB"""

    id: int = Field(..., alias="_id")
    run_id: int
    name: Optional[str] = None
    status: Optional[str] = None
    conclusion: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    steps: Optional[list] = None
    labels: Optional[list] = None
    runner_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
