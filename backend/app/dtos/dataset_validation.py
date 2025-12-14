"""DTOs for dataset validation API."""

from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field

from app.entities import ValidationStats


# ============================================================================
# Request DTOs
# ============================================================================


class RepoConfigRequest(BaseModel):
    """Request model for saving repos from Step 2."""

    full_name: str
    ci_provider: str = "github_actions"
    source_languages: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)
    validation_status: str = "valid"


class SaveReposRequest(BaseModel):
    """Request to save multiple repo configurations."""

    repos: List[RepoConfigRequest]


# ============================================================================
# Response DTOs
# ============================================================================


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
    full_name: str
    validation_status: str
    validation_error: Optional[str] = None
    builds_found: Optional[int] = None
    builds_not_found: Optional[int] = None


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
