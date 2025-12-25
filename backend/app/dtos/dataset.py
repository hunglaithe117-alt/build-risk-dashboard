"""DTOs for dataset projects (uploaded CSVs for enrichment)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr


class DatasetMappingDto(BaseModel):
    build_id: Optional[str] = None
    repo_name: Optional[str] = None


class DatasetStatsDto(BaseModel):
    missing_rate: float = 0.0
    duplicate_rate: float = 0.0
    build_coverage: float = 0.0


class RepoValidationStatsDto(BaseModel):
    """Per-repository validation statistics."""

    full_name: str
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0
    builds_filtered: int = 0
    is_valid: bool = True
    error: Optional[str] = None


class ValidationStatsDto(BaseModel):
    repos_total: int = 0
    repos_valid: int = 0
    repos_invalid: int = 0
    repos_not_found: int = 0
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0
    builds_filtered: int = 0
    repo_stats: List[RepoValidationStatsDto] = Field(default_factory=list)


class BuildValidationFiltersDto(BaseModel):
    """Filters applied during build validation."""

    exclude_bots: bool = False
    only_completed: bool = True

    # Available: success, failure, cancelled, skipped, timed_out, action_required, neutral, stale
    allowed_conclusions: List[str] = Field(default_factory=lambda: ["success", "failure"])


class DatasetResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
    user_id: Optional[PyObjectIdStr] = None
    name: str
    description: Optional[str] = None
    file_name: str
    file_path: Optional[str] = None
    source: str
    rows: int
    size_bytes: int
    columns: List[str]
    mapped_fields: DatasetMappingDto = Field(default_factory=DatasetMappingDto)
    stats: DatasetStatsDto = Field(default_factory=DatasetStatsDto)
    preview: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None

    # CI Provider
    ci_provider: Optional[str] = None

    # Build validation filters
    build_filters: BuildValidationFiltersDto = Field(default_factory=BuildValidationFiltersDto)

    # Validation status fields (unified validation)
    validation_status: str = "pending"
    validation_task_id: Optional[str] = None
    validation_started_at: Optional[datetime] = None
    validation_completed_at: Optional[datetime] = None
    validation_progress: int = 0
    validation_stats: ValidationStatsDto = Field(default_factory=ValidationStatsDto)
    validation_error: Optional[str] = None

    # Setup progress tracking (1=uploaded, 2=validated)
    setup_step: int = 1

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class DatasetListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[DatasetResponse]


class DatasetCreateRequest(BaseModel):
    name: str
    file_name: str
    rows: int
    size_bytes: int
    columns: List[str]
    description: Optional[str] = None
    source: str = "upload"
    mapped_fields: Optional[DatasetMappingDto] = None
    stats: Optional[DatasetStatsDto] = None
    preview: List[Dict[str, Any]] = Field(default_factory=list)


class RepoValidationItem(BaseModel):
    """Single repo validation result."""

    repo_name: str
    status: str  # "exists", "not_found", "error", "invalid_format"
    build_count: int = 0  # Number of builds in CSV for this repo
    message: Optional[str] = None


class RepoValidationResponse(BaseModel):
    """Response for GitHub repo validation."""

    total_repos: int
    valid_repos: int
    invalid_repos: int
    repos: List[RepoValidationItem]


class DatasetUpdateRequest(BaseModel):
    """Request for updating dataset (PATCH)."""

    name: Optional[str] = None
    description: Optional[str] = None
    mapped_fields: Optional[DatasetMappingDto] = None
    ci_provider: Optional[str] = None
    build_filters: Optional[BuildValidationFiltersDto] = None
    setup_step: Optional[int] = None
