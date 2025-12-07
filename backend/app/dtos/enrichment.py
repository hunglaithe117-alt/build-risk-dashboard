"""DTOs for Dataset Enrichment API."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Request DTOs
# ============================================================================

class EnrichmentValidateRequest(BaseModel):
    """Request to validate dataset for enrichment."""
    pass  # No body needed, dataset_id from path


class EnrichmentStartRequest(BaseModel):
    """Request to start dataset enrichment."""
    selected_features: List[str] = Field(
        default_factory=list,
        description="List of feature IDs to extract"
    )
    auto_import_repos: bool = Field(
        default=True,
        description="Auto-import missing repositories"
    )
    skip_existing: bool = Field(
        default=True,
        description="Skip rows that already have features extracted"
    )


class EnrichmentCancelRequest(BaseModel):
    """Request to cancel enrichment job."""
    pass  # No body needed


# ============================================================================
# Response DTOs
# ============================================================================

class EnrichmentValidateResponse(BaseModel):
    """Response from dataset validation."""
    valid: bool = Field(..., description="Whether dataset can be enriched")
    total_rows: int = Field(..., description="Total rows in dataset")
    enrichable_rows: int = Field(..., description="Rows that can be enriched")
    repos_found: List[str] = Field(
        default_factory=list,
        description="Repositories already in system"
    )
    repos_missing: List[str] = Field(
        default_factory=list,
        description="Repositories not in system (will be auto-imported)"
    )
    repos_invalid: List[str] = Field(
        default_factory=list,
        description="Invalid repository names"
    )
    mapping_complete: bool = Field(
        ..., description="Whether required field mapping is complete"
    )
    missing_mappings: List[str] = Field(
        default_factory=list,
        description="Required fields not mapped"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Validation errors"
    )


class EnrichmentJobResponse(BaseModel):
    """Response with enrichment job details."""
    id: str
    dataset_id: str
    status: str
    total_rows: int = 0
    processed_rows: int = 0
    enriched_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0
    progress_percent: float = 0.0
    selected_features: List[str] = Field(default_factory=list)
    repos_auto_imported: List[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    output_file: Optional[str] = None
    created_at: Optional[datetime] = None


class EnrichmentStartResponse(BaseModel):
    """Response when starting enrichment."""
    job_id: str = Field(..., description="Enrichment job ID")
    status: str = Field(default="pending")
    message: str = Field(default="Enrichment job started")
    websocket_url: Optional[str] = Field(
        None,
        description="WebSocket URL for real-time progress"
    )


class EnrichmentStatusResponse(BaseModel):
    """Response with enrichment status."""
    job_id: str
    status: str
    progress_percent: float
    processed_rows: int
    total_rows: int
    enriched_rows: int
    failed_rows: int
    repos_auto_imported: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    output_file: Optional[str] = None
    estimated_time_remaining_seconds: Optional[float] = None


class EnrichmentRowErrorResponse(BaseModel):
    """Error details for a single row."""
    row_index: int
    error: str


class EnrichmentJobListResponse(BaseModel):
    """Response with list of enrichment jobs."""
    items: List[EnrichmentJobResponse]
    total: int


# ============================================================================
# WebSocket Event DTOs
# ============================================================================

class EnrichmentProgressEvent(BaseModel):
    """WebSocket event for progress update."""
    type: str = "progress"
    job_id: str
    processed_rows: int
    total_rows: int
    enriched_rows: int
    failed_rows: int
    progress_percent: float
    current_repo: Optional[str] = None


class EnrichmentRowCompleteEvent(BaseModel):
    """WebSocket event when a row is processed."""
    type: str = "row_complete"
    job_id: str
    row_index: int
    success: bool
    repo_name: Optional[str] = None
    features_extracted: int = 0
    error: Optional[str] = None


class EnrichmentCompleteEvent(BaseModel):
    """WebSocket event when job completes."""
    type: str = "complete"
    job_id: str
    status: str
    total_rows: int
    enriched_rows: int
    failed_rows: int
    output_file: Optional[str] = None
    duration_seconds: Optional[float] = None


class EnrichmentErrorEvent(BaseModel):
    """WebSocket event for errors."""
    type: str = "error"
    job_id: str
    message: str
    row_index: Optional[int] = None
