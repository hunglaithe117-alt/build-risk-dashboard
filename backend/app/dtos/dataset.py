"""DTOs for dataset projects (uploaded CSVs for enrichment)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr


class DatasetMappingDto(BaseModel):
    build_id: Optional[str] = None
    commit_sha: Optional[str] = None
    repo_name: Optional[str] = None
    timestamp: Optional[str] = None


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
    source: str
    rows: int
    size_mb: float
    columns: List[str]
    mapped_fields: DatasetMappingDto = Field(default_factory=DatasetMappingDto)
    stats: DatasetStatsDto = Field(default_factory=DatasetStatsDto)
    tags: List[str] = Field(default_factory=list)
    selected_template: Optional[str] = None
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
    size_mb: float
    columns: List[str]
    description: Optional[str] = None
    source: str = "upload"
    mapped_fields: Optional[DatasetMappingDto] = None
    stats: Optional[DatasetStatsDto] = None
    tags: List[str] = Field(default_factory=list)
    selected_template: Optional[str] = None
    selected_features: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mapped_fields: Optional[DatasetMappingDto] = None
    stats: Optional[DatasetStatsDto] = None
    tags: Optional[List[str]] = None
    selected_template: Optional[str] = None
    selected_features: Optional[List[str]] = None
