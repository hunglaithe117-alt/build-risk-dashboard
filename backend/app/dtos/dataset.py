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


class ValidationStatsDto(BaseModel):

    repos_total: int = 0
    repos_valid: int = 0
    repos_invalid: int = 0
    repos_not_found: int = 0
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0


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

    # Validation status fields (build validation - Step 3)
    validation_status: str = "pending"
    validation_task_id: Optional[str] = None
    validation_started_at: Optional[datetime] = None
    validation_completed_at: Optional[datetime] = None
    validation_progress: int = 0
    validation_stats: ValidationStatsDto = Field(default_factory=ValidationStatsDto)
    validation_error: Optional[str] = None

    # Repo validation status (during upload - before Step 2)
    repo_validation_status: str = "pending"
    repo_validation_task_id: Optional[str] = None
    repo_validation_error: Optional[str] = None

    # Setup progress tracking (1=uploaded, 2=configured, 3=validated)
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


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mapped_fields: Optional[DatasetMappingDto] = None
    stats: Optional[DatasetStatsDto] = None
    source_languages: Optional[List[str]] = None
    test_frameworks: Optional[List[str]] = None
    setup_step: Optional[int] = None


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
