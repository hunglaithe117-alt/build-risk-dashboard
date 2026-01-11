from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.entities.base import PyObjectIdStr


class DatasetTemplateResponse(BaseModel):
    """Response DTO for dataset template."""

    id: Optional[PyObjectIdStr] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    feature_names: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    source: str = "seed"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class DatasetTemplateListResponse(BaseModel):
    """List response for dataset templates."""

    total: int
    items: List[DatasetTemplateResponse]
