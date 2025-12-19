"""DTOs for DatasetRepoConfig responses."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr


class DatasetRepoSummary(BaseModel):
    """Summary DTO for dataset repo in list view."""

    id: PyObjectIdStr = Field(..., alias="_id")
    raw_repo_id: Optional[PyObjectIdStr] = None
    repo_name: str  # Maps to full_name from entity
    validation_status: str
    validation_error: Optional[str] = None
    builds_in_csv: int = 0
    builds_found: int = 0
    builds_processed: int = 0

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class DatasetRepoListResponse(BaseModel):
    """Response DTO for listing repos in a dataset."""

    items: List[DatasetRepoSummary]
    total: int
