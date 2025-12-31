"""DTOs for Build API - RawBuildRun as primary source with optional training enrichment."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BuildSummary(BaseModel):
    """
    Summary of a CI build from ModelTrainingBuild with RawBuildRun enrichment.

    Primary data comes from ModelTrainingBuild (builds that have been processed).
    Additional data (conclusion, branch, etc.) comes from RawBuildRun.
    """

    # Identity - using RawBuildRun._id as primary key
    id: str = Field(..., alias="_id")

    # From RawBuildRun - always available after ingestion
    build_number: Optional[int] = None
    build_id: str = ""  # CI provider's build ID (e.g., GitHub run ID)
    conclusion: str = "unknown"  # success, failure, cancelled, etc.
    commit_sha: str = ""
    branch: str = ""
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    web_url: Optional[str] = None

    # Logs info from RawBuildRun
    logs_available: Optional[bool] = None
    logs_expired: bool = False

    # Training data from ModelTrainingBuild (always present since we query from training builds)
    has_training_data: bool = False
    training_build_id: Optional[str] = None
    extraction_status: Optional[str] = None  # pending, completed, failed, partial
    feature_count: int = 0
    extraction_error: Optional[str] = None
    missing_resources: List[str] = []

    # Prediction
    predicted_label: Optional[str] = None
    prediction_confidence: Optional[float] = None

    class Config:
        populate_by_name = True


class BuildDetail(BaseModel):
    """
    Detailed view of a build with full RawBuildRun data and training features.
    """

    # Identity
    id: str = Field(..., alias="_id")

    # From RawBuildRun
    build_number: Optional[int] = None
    build_id: str = ""
    conclusion: str = "unknown"
    commit_sha: str = ""
    branch: str = ""
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    web_url: Optional[str] = None
    provider: str = "github_actions"

    # Logs
    logs_available: Optional[bool] = None
    logs_expired: bool = False

    # Training enrichment
    has_training_data: bool = False
    training_build_id: Optional[str] = None
    extraction_status: Optional[str] = None
    feature_count: int = 0
    extraction_error: Optional[str] = None
    features: Dict[str, Any] = {}

    # Prediction results
    predicted_label: Optional[str] = None  # LOW, MEDIUM, HIGH
    prediction_confidence: Optional[float] = None  # 0-1 score
    prediction_uncertainty: Optional[float] = None
    predicted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class BuildListResponse(BaseModel):
    """Paginated list of builds."""

    items: List[BuildSummary]
    total: int
    page: int
    size: int


# =============================================================================
# Import Build DTOs (Ingestion Phase)
# =============================================================================


class ResourceStatusDTO(BaseModel):
    """Status of a single resource in ingestion."""

    status: str = "pending"  # pending, in_progress, completed, failed, skipped
    error: Optional[str] = None


class ImportBuildSummary(BaseModel):
    """
    Summary of a build in the import/ingestion phase.

    Shows RawBuildRun basics + ModelImportBuild status + resource breakdown.
    """

    # Identity - using ModelImportBuild._id
    id: str = Field(..., alias="_id")

    # From RawBuildRun (denormalized)
    build_number: Optional[int] = None
    build_id: str = ""  # CI provider's build ID
    commit_sha: str = ""
    branch: str = ""
    conclusion: str = "unknown"  # Build result (success/failure)
    created_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    web_url: Optional[str] = None
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None
    duration_seconds: Optional[float] = None

    # From ModelImportBuild
    status: str = "fetched"  # pending, fetched, ingesting, ingested, failed
    ingestion_started_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None

    # Resource status breakdown
    resource_status: Dict[str, ResourceStatusDTO] = {}
    required_resources: List[str] = []

    class Config:
        populate_by_name = True


class ImportBuildListResponse(BaseModel):
    """Paginated list of import builds."""

    items: List[ImportBuildSummary]
    total: int
    page: int
    size: int


# =============================================================================
# Training Build DTOs (Processing Phase)
# =============================================================================


class TrainingBuildSummary(BaseModel):
    """
    Summary of a build in the processing/training phase.

    Shows ModelTrainingBuild status + feature extraction + prediction.
    """

    # Identity - using ModelTrainingBuild._id
    id: str = Field(..., alias="_id")

    # Build basics (from RawBuildRun via joins)
    build_number: Optional[int] = None
    build_id: str = ""
    commit_sha: str = ""
    branch: str = ""
    conclusion: str = "unknown"
    created_at: Optional[datetime] = None
    web_url: Optional[str] = None

    # Extraction status
    extraction_status: str = "pending"  # pending, completed, failed, partial
    extraction_error: Optional[str] = None
    extracted_at: Optional[datetime] = None
    feature_count: int = 0
    skipped_features: List[str] = []
    missing_resources: List[str] = []

    # Prediction results
    predicted_label: Optional[str] = None  # LOW, MEDIUM, HIGH
    prediction_confidence: Optional[float] = None
    prediction_uncertainty: Optional[float] = None
    predicted_at: Optional[datetime] = None

    class Config:
        populate_by_name = True


class TrainingBuildListResponse(BaseModel):
    """Paginated list of training builds."""

    items: List[TrainingBuildSummary]
    total: int
    page: int
    size: int


# =============================================================================
# Enrichment Build Detail DTOs (for dataset version build detail page)
# =============================================================================


class NodeExecutionDetail(BaseModel):
    """Detail of a single node execution within a pipeline run."""

    node_name: str
    status: str  # success, failed, skipped
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    features_extracted: List[str] = []
    resources_used: List[str] = []
    error: Optional[str] = None
    warning: Optional[str] = None
    skip_reason: Optional[str] = None
    retry_count: int = 0


class AuditLogDetail(BaseModel):
    """Extraction audit log details from FeatureAuditLog."""

    id: str
    correlation_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    # Node statistics
    nodes_executed: int = 0
    nodes_succeeded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0
    total_retries: int = 0

    # Feature summary
    feature_count: int = 0
    features_extracted: List[str] = []

    # Issues
    errors: List[str] = []
    warnings: List[str] = []

    # Node execution details
    node_results: List[NodeExecutionDetail] = []


class RawBuildRunDetail(BaseModel):
    """Build run info from RawBuildRun entity."""

    id: str
    ci_run_id: str
    build_number: Optional[int] = None
    repo_name: str = ""
    branch: str = ""
    commit_sha: str = ""
    commit_message: Optional[str] = None
    commit_author: Optional[str] = None
    status: str = "unknown"
    conclusion: str = "none"
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    web_url: Optional[str] = None
    provider: str = "github_actions"
    logs_available: Optional[bool] = None
    logs_expired: bool = False
    is_bot_commit: Optional[bool] = None


class EnrichmentBuildDetail(BaseModel):
    """Enrichment build info from DatasetEnrichmentBuild entity."""

    id: str
    extraction_status: str = "pending"
    extraction_error: Optional[str] = None
    is_missing_commit: bool = False
    missing_resources: List[str] = []
    skipped_features: List[str] = []
    feature_count: int = 0
    expected_feature_count: int = 0
    features: Dict[str, Any] = {}
    scan_metrics: Dict[str, Any] = {}
    enriched_at: Optional[datetime] = None


class EnrichmentBuildDetailResponse(BaseModel):
    """
    Complete build detail for dataset version enriched build.

    Aggregates data from:
    - RawBuildRun: CI build metadata
    - DatasetEnrichmentBuild: Extracted features
    - FeatureAuditLog: Extraction logs
    """

    raw_build_run: RawBuildRunDetail
    enrichment_build: EnrichmentBuildDetail
    audit_log: Optional[AuditLogDetail] = None
