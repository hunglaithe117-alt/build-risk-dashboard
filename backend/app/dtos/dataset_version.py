from typing import List, Optional

from pydantic import BaseModel, Field


class CreateVersionRequest(BaseModel):
    """Request to create a new dataset version."""

    selected_features: List[str] = Field(
        ..., min_length=1, description="List of feature names to extract"
    )
    name: Optional[str] = Field(None, description="Optional version name")
    description: Optional[str] = Field(None, description="Optional description")


class VersionResponse(BaseModel):
    """Response for a single version."""

    id: str
    dataset_id: str
    version_number: int
    name: str
    description: Optional[str]
    selected_features: List[str]
    status: str
    total_rows: int
    processed_rows: int
    enriched_rows: int
    failed_rows: int
    skipped_rows: int
    progress_percent: float
    file_name: Optional[str]
    file_size_bytes: Optional[int]
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """Response for listing versions."""

    versions: List[VersionResponse]
    total: int
