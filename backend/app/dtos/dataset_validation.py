"""DTOs for dataset validation API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.entities import ValidationStats


class RepoConfigRequest(BaseModel):
    """Request model for updating repos from Step 2."""

    id: str  # DatasetRepoConfig id
    ci_provider: str = "github_actions"
    source_languages: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)


class SaveReposRequest(BaseModel):
    """Request to update multiple repo configurations."""

    repos: List[RepoConfigRequest]


class ValidationStatusResponse(BaseModel):
    """Response for validation status check."""

    dataset_id: str
    status: str
    progress: int = 0
    task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    stats: Optional[ValidationStats] = None


class StartValidationResponse(BaseModel):
    """Response when starting validation."""

    task_id: str
    message: str


class RepoValidationResult(BaseModel):
    """Validation result for a single repository."""

    id: str
    raw_repo_id: str
    github_repo_id: Optional[int] = None  # Needed for per-repo scan config
    full_name: str
    ci_provider: str = "github_actions"
    validation_status: str
    validation_error: Optional[str] = None
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0


class ValidationSummaryResponse(BaseModel):
    """Detailed validation summary including repo breakdown."""

    dataset_id: str
    status: str
    stats: ValidationStats
    repos: list[RepoValidationResult] = Field(default_factory=list)


class SaveReposResponse(BaseModel):
    """Response for save repos operation."""

    saved: int
    message: str
