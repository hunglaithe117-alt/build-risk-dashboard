"""DTOs for dataset projects (uploaded CSVs for enrichment)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr


class DatasetMappingDto(BaseModel):
    build_id: Optional[str] = None
    repo_name: Optional[str] = None


class DatasetStatsDto(BaseModel):
    coverage: float = 0.0
    missing_rate: float = 0.0
    duplicate_rate: float = 0.0
    build_coverage: float = 0.0


class DatasetResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
    user_id: Optional[PyObjectIdStr] = None
    name: str
    description: Optional[str] = None
    file_name: str
    file_path: Optional[str] = None
    source: str
    ci_provider: str = "github_actions"
    rows: int
    size_bytes: int
    columns: List[str]
    mapped_fields: DatasetMappingDto = Field(default_factory=DatasetMappingDto)
    stats: DatasetStatsDto = Field(default_factory=DatasetStatsDto)
    selected_features: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None

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
    selected_features: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mapped_fields: Optional[DatasetMappingDto] = None
    stats: Optional[DatasetStatsDto] = None
    selected_features: Optional[List[str]] = None


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
