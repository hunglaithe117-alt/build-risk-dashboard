"""Integration/Scan DTOs."""

from typing import List, Optional

from pydantic import BaseModel

# =============================================================================
# Tool DTOs
# =============================================================================


class ToolInfoResponse(BaseModel):
    """Response DTO for tool information."""

    type: str
    display_name: str
    description: str
    scan_mode: str
    is_available: bool
    config: dict
    scan_types: List[str]
    metric_count: int


class ToolsListResponse(BaseModel):
    """Response DTO for tools list."""

    tools: List[ToolInfoResponse]


# =============================================================================
# Scan DTOs
# =============================================================================


class StartScanRequest(BaseModel):
    """Request DTO to start a scan."""

    tool_type: str  # "sonarqube" or "trivy"
    scan_config: Optional[str] = None  # Default config for all commits


class ScanResponse(BaseModel):
    """Response DTO for a scan."""

    id: str
    dataset_id: str
    tool_type: str
    status: str
    total_commits: int
    scanned_commits: int
    failed_commits: int
    pending_commits: int
    progress_percentage: float
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ScansListResponse(BaseModel):
    """Response DTO for scans list."""

    scans: List[ScanResponse]
    total: int


class ScanDetailResponse(BaseModel):
    """Response DTO for scan details."""

    id: str
    dataset_id: str
    tool_type: str
    status: str
    total_commits: int
    scanned_commits: int
    failed_commits: int
    pending_commits: int
    progress_percentage: float
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    results_summary: Optional[dict] = None
    error_message: Optional[str] = None


# =============================================================================
# Scan Result DTOs
# =============================================================================


class ScanResultResponse(BaseModel):
    """Response DTO for a single scan result."""

    id: str
    commit_sha: str
    repo_full_name: str
    row_indices: List[int]
    status: str
    results: dict
    error_message: Optional[str] = None
    scan_duration_ms: Optional[int] = None


class ScanResultsListResponse(BaseModel):
    """Response DTO for scan results list."""

    results: List[ScanResultResponse]
    total: int


class ScanSummaryResponse(BaseModel):
    """Response DTO for scan summary."""

    scan_id: str
    tool_type: str
    status: str
    progress: float
    total_commits: int
    status_counts: dict
    aggregated_metrics: dict


# =============================================================================
# Failed Results DTOs
# =============================================================================


class FailedResultResponse(BaseModel):
    """Response DTO for a failed scan result."""

    id: str
    commit_sha: str
    repo_full_name: str
    error_message: Optional[str] = None
    retry_count: int = 0
    override_config: Optional[str] = None


class FailedResultsListResponse(BaseModel):
    """Response DTO for failed results list."""

    results: List[FailedResultResponse]
    total: int


class RetryResultRequest(BaseModel):
    """Request DTO to retry a failed result."""

    override_config: Optional[str] = None  # Per-commit config override


# =============================================================================
# Webhook DTOs
# =============================================================================


class SonarWebhookPayload(BaseModel):
    """Payload DTO for SonarQube webhook."""

    project: dict
    status: str
    analysedAt: Optional[str] = None
