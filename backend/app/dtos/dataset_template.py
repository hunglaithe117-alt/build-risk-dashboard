"""DTOs for dataset templates (seeded datasets to help feature selection)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr
from .dataset import DatasetMappingDto, DatasetStatsDto


class DatasetTemplateResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
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


class DatasetTemplateListResponse(BaseModel):
    total: int
    items: List[DatasetTemplateResponse]
