from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateVersionRequest(BaseModel):
    """Request to create a new dataset version."""

    selected_features: List[str] = Field(
        ..., min_length=1, description="List of feature names to extract"
    )
    feature_configs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Feature configuration values (global and per-repo)",
    )
    scan_metrics: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Scan metrics to include: {'sonarqube': [...], 'trivy': [...]}",
    )
    scan_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Scan tool configuration: {'sonarqube': {...}, 'trivy': {...}}",
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
    skip: int = 0
    limit: int = 10
