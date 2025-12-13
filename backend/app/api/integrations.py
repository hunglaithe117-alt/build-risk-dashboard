from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.github import (
    GithubInstallationListResponse,
    GithubInstallationResponse,
)
from app.middleware.auth import get_current_user
from app.services.integration_service import IntegrationService
from app.services.dataset_scan_service import DatasetScanService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# =============================================================================
# GitHub Installations (existing)
# =============================================================================


@router.get(
    "/github/installations",
    response_model=GithubInstallationListResponse,
    response_model_by_alias=False,
)
def list_github_installations(
    db: Database = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    service = IntegrationService(db)
    return service.list_github_installations()


@router.get(
    "/github/installations/{installation_id}",
    response_model=GithubInstallationResponse,
    response_model_by_alias=False,
)
def get_github_installation(
    installation_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = IntegrationService(db)
    return service.get_github_installation(installation_id)


@router.post(
    "/github/sync",
    response_model=GithubInstallationListResponse,
    response_model_by_alias=False,
)
def sync_github_installations(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Sync GitHub App installations from GitHub API."""
    service = IntegrationService(db)
    return service.sync_installations(current_user["_id"])


# =============================================================================
# Scanning Tools (new)
# =============================================================================


class ToolInfoResponse(BaseModel):
    type: str
    display_name: str
    description: str
    scan_mode: str
    is_available: bool
    config: dict
    scan_types: List[str]
    metric_count: int


class ToolsListResponse(BaseModel):
    tools: List[ToolInfoResponse]


@router.get("/tools", response_model=ToolsListResponse)
def list_tools(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List available integration tools with their status."""
    service = DatasetScanService(db)
    tools = service.get_available_tools()
    return {"tools": tools}


# =============================================================================
# Dataset Scanning
# =============================================================================


class UniqueCommitInfo(BaseModel):
    sha: str
    repo_full_name: str
    row_count: int
    row_indices: List[int]
    last_scanned: Optional[str] = None
    scan_results: Optional[dict] = None


class UniqueCommitsResponse(BaseModel):
    commits: List[UniqueCommitInfo]
    total: int


@router.get("/datasets/{dataset_id}/commits", response_model=UniqueCommitsResponse)
def get_unique_commits(
    dataset_id: str,
    version_id: Optional[str] = None,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get unique commits from dataset for scan selection."""
    service = DatasetScanService(db)
    commits = service.get_unique_commits(dataset_id, version_id)
    return {"commits": commits, "total": len(commits)}


class StartScanRequest(BaseModel):
    tool_type: str  # "sonarqube" or "trivy"
    selected_commit_shas: Optional[List[str]] = None  # None = all


class ScanResponse(BaseModel):
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


@router.post("/datasets/{dataset_id}/scans", response_model=ScanResponse)
def start_scan(
    dataset_id: str,
    request: StartScanRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Start a new scan job for a dataset."""
    service = DatasetScanService(db)
    try:
        scan = service.start_scan(
            dataset_id=dataset_id,
            user_id=str(current_user["_id"]),
            tool_type=request.tool_type,
            selected_commit_shas=request.selected_commit_shas,
        )
        return {
            "id": str(scan.id),
            "dataset_id": str(scan.dataset_id),
            "tool_type": scan.tool_type,
            "status": scan.status.value,
            "total_commits": scan.total_commits,
            "scanned_commits": scan.scanned_commits,
            "failed_commits": scan.failed_commits,
            "pending_commits": scan.pending_commits,
            "progress_percentage": scan.progress_percentage,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "completed_at": (
                scan.completed_at.isoformat() if scan.completed_at else None
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ScansListResponse(BaseModel):
    scans: List[ScanResponse]
    total: int


@router.get("/datasets/{dataset_id}/scans", response_model=ScansListResponse)
def list_scans(
    dataset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List scans for a dataset with pagination."""
    service = DatasetScanService(db)
    scans, total = service.list_scans(dataset_id, skip=skip, limit=limit)
    return {
        "scans": [
            {
                "id": str(s.id),
                "dataset_id": str(s.dataset_id),
                "tool_type": s.tool_type,
                "status": s.status.value,
                "total_commits": s.total_commits,
                "scanned_commits": s.scanned_commits,
                "failed_commits": s.failed_commits,
                "pending_commits": s.pending_commits,
                "progress_percentage": s.progress_percentage,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in scans
        ],
        "total": total,
    }


class ScanDetailResponse(BaseModel):
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


@router.get("/datasets/{dataset_id}/scans/{scan_id}", response_model=ScanDetailResponse)
def get_scan(
    dataset_id: str,
    scan_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get scan details."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    return {
        "id": str(scan.id),
        "dataset_id": str(scan.dataset_id),
        "tool_type": scan.tool_type,
        "status": scan.status.value,
        "total_commits": scan.total_commits,
        "scanned_commits": scan.scanned_commits,
        "failed_commits": scan.failed_commits,
        "pending_commits": scan.pending_commits,
        "progress_percentage": scan.progress_percentage,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
        "results_summary": scan.results_summary,
        "error_message": scan.error_message,
    }


@router.delete("/datasets/{dataset_id}/scans/{scan_id}")
def cancel_scan(
    dataset_id: str,
    scan_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a running scan."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    success = service.cancel_scan(scan_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this scan")

    return {"status": "cancelled"}


class ScanResultResponse(BaseModel):
    id: str
    commit_sha: str
    repo_full_name: str
    row_indices: List[int]
    status: str
    results: dict
    error_message: Optional[str] = None
    scan_duration_ms: Optional[int] = None


class ScanResultsListResponse(BaseModel):
    results: List[ScanResultResponse]
    total: int


@router.get(
    "/datasets/{dataset_id}/scans/{scan_id}/results",
    response_model=ScanResultsListResponse,
)
def get_scan_results(
    dataset_id: str,
    scan_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get scan results with pagination."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    results, total = service.get_scan_results(scan_id, skip=skip, limit=limit)
    return {
        "results": [
            {
                "id": str(r.id),
                "commit_sha": r.commit_sha,
                "repo_full_name": r.repo_full_name,
                "row_indices": r.row_indices,
                "status": r.status,
                "results": r.results,
                "error_message": r.error_message,
                "scan_duration_ms": r.scan_duration_ms,
            }
            for r in results
        ],
        "total": total,
    }


class ScanSummaryResponse(BaseModel):
    scan_id: str
    tool_type: str
    status: str
    progress: float
    total_commits: int
    status_counts: dict
    aggregated_metrics: dict


@router.get(
    "/datasets/{dataset_id}/scans/{scan_id}/summary",
    response_model=ScanSummaryResponse,
)
def get_scan_summary(
    dataset_id: str,
    scan_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get aggregated summary of scan results."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    summary = service.get_scan_summary(scan_id)
    return summary


# =============================================================================
# SonarQube Webhook
# =============================================================================


class SonarWebhookPayload(BaseModel):
    project: dict
    status: str
    analysedAt: Optional[str] = None


@router.post("/webhooks/sonarqube")
async def sonarqube_webhook(
    payload: SonarWebhookPayload,
    db: Database = Depends(get_db),
):
    """
    Handle SonarQube webhook callback.

    Called by SonarQube when analysis completes.
    """
    component_key = payload.project.get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="Missing project key")

    # Check if this is for a dataset scan
    service = DatasetScanService(db)

    # Fetch metrics from SonarQube
    from app.services.sonar.exporter import MetricsExporter

    exporter = MetricsExporter()

    try:
        metrics = exporter.collect_metrics(component_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {e}")

    # Update result
    result = service.handle_sonar_webhook(component_key, metrics)

    if result:
        return {"status": "processed", "result_id": str(result.id)}
    else:
        # Not a dataset scan, might be from old pipeline
        return {"status": "ignored", "reason": "No matching dataset scan result"}
