"""DTOs for dataset templates (feature presets for repo import)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr


class DatasetTemplateResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
    name: str
    description: Optional[str] = None
    feature_names: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    source: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class DatasetTemplateListResponse(BaseModel):
    total: int
    items: List[DatasetTemplateResponse]
