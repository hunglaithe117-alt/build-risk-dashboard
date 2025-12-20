import asyncio
from typing import Optional, Set

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    FailedResultsListResponse,
    RetryResultRequest,
    ScanDetailResponse,
    ScanResponse,
    ScanResultResponse,
    ScanResultsListResponse,
    ScansListResponse,
    ScanSummaryResponse,
    SonarWebhookPayload,
    StartScanRequest,
    ToolsListResponse,
)
from app.middleware.auth import get_current_user
from app.middleware.rbac import require_view_scans
from app.middleware.require_dataset_manager import require_dataset_manager
from app.services.dataset_scan_service import DatasetScanService
from app.services.sonar_webhook_service import SonarWebhookService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# =============================================================================
# GitHub Installations (DEPRECATED/REMOVED)
# We now use single-tenant config GITHUB_INSTALLATION_ID.
# =============================================================================


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


@router.post("/datasets/{dataset_id}/scans", response_model=ScanResponse)
def start_scan(
    dataset_id: str,
    request: StartScanRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_dataset_manager),
):
    """Start a new scan job for a dataset. Scans all validated builds (Admin and Guest)."""
    service = DatasetScanService(db)
    try:
        scan = service.start_scan(
            dataset_id=dataset_id,
            user_id=str(current_user["_id"]),
            tool_type=request.tool_type,
            scan_config=request.scan_config,
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
            "completed_at": (scan.completed_at.isoformat() if scan.completed_at else None),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/datasets/{dataset_id}/scans", response_model=ScansListResponse)
def list_scans(
    dataset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
    _viewer: dict = Depends(require_view_scans),
):
    """List scans for a dataset with pagination (Admin + Guest)."""
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


@router.get("/datasets/{dataset_id}/scans/{scan_id}", response_model=ScanDetailResponse)
def get_scan(
    dataset_id: str,
    scan_id: str,
    db: Database = Depends(get_db),
    _viewer: dict = Depends(require_view_scans),
):
    """Get scan details (Admin + Guest)."""
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
    _current_user: dict = Depends(require_dataset_manager),
):
    """Cancel a running scan (Admin and Guest)."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    success = service.cancel_scan(scan_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel this scan")

    return {"status": "cancelled"}


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
    _viewer: dict = Depends(require_view_scans),
):
    """Get scan results with pagination (Admin + Guest)."""
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


@router.get(
    "/datasets/{dataset_id}/scans/{scan_id}/summary",
    response_model=ScanSummaryResponse,
)
def get_scan_summary(
    dataset_id: str,
    scan_id: str,
    db: Database = Depends(get_db),
    _viewer: dict = Depends(require_view_scans),
):
    """Get aggregated summary of scan results (Admin + Guest)."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    summary = service.get_scan_summary(scan_id)
    return summary


# =============================================================================
# Failed Results and Retry
# =============================================================================


@router.get(
    "/datasets/{dataset_id}/scans/{scan_id}/failed",
    response_model=FailedResultsListResponse,
)
def get_failed_results(
    dataset_id: str,
    scan_id: str,
    db: Database = Depends(get_db),
    _viewer: dict = Depends(require_view_scans),
):
    """Get failed results for retry UI (Admin + Guest read-only view)."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    results = service.get_failed_results(scan_id)
    return {
        "results": [
            {
                "id": str(r.id),
                "commit_sha": r.commit_sha,
                "repo_full_name": r.repo_full_name,
                "error_message": r.error_message,
                "retry_count": r.retry_count,
                "override_config": r.override_config,
            }
            for r in results
        ],
        "total": len(results),
    }


@router.post(
    "/datasets/{dataset_id}/scans/{scan_id}/results/{result_id}/retry",
    response_model=ScanResultResponse,
)
def retry_result(
    dataset_id: str,
    scan_id: str,
    result_id: str,
    request: RetryResultRequest,
    db: Database = Depends(get_db),
    _current_user: dict = Depends(require_dataset_manager),
):
    """Retry a failed scan result with optional config override (Admin and Guest)."""
    service = DatasetScanService(db)
    scan = service.get_scan(scan_id)
    if not scan or str(scan.dataset_id) != dataset_id:
        raise HTTPException(status_code=404, detail="Scan not found")

    result = service.retry_failed_result(result_id, request.override_config)
    if not result:
        raise HTTPException(status_code=400, detail="Cannot retry this result")

    return {
        "id": str(result.id),
        "commit_sha": result.commit_sha,
        "repo_full_name": result.repo_full_name,
        "row_indices": result.row_indices,
        "status": result.status,
        "results": result.results,
        "error_message": result.error_message,
        "scan_duration_ms": result.scan_duration_ms,
    }


# =============================================================================
# SonarQube Webhook
# =============================================================================


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
    from app.integrations.tools.sonarqube.exporter import MetricsExporter

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


# =============================================================================
# SonarQube Pipeline Webhook (from old sonar.py)
# =============================================================================

import json


@router.post("/webhooks/sonarqube/pipeline")
async def sonarqube_pipeline_webhook(
    request: Request,
    db: Database = Depends(get_db),
    x_sonar_webhook_hmac_sha256: Optional[str] = Header(default=None),
    x_sonar_secret: Optional[str] = Header(default=None),
):
    """
    Handle SonarQube webhook callback for pipeline-initiated scans.

    This is called by SonarQube when analysis completes for pipeline scans.
    """
    body = await request.body()

    service = SonarWebhookService(db)
    service.validate_signature(body, x_sonar_webhook_hmac_sha256, x_sonar_secret)

    payload = json.loads(body.decode("utf-8") or "{}")

    component_key = payload.get("project", {}).get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="project key missing")

    task_status = payload.get("status")

    return service.handle_pipeline_webhook(component_key, task_status)


@router.get("/sonar/pending/{component_key}")
async def get_sonar_pending_scan(
    component_key: str,
    db: Database = Depends(get_db),
):
    """Check status of a pending SonarQube scan."""
    service = SonarWebhookService(db)
    return service.get_pending_scan(component_key)


@router.get("/sonar/datasets/{dataset_id}/pending")
async def get_sonar_dataset_pending_scans(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Get all pending scans for a dataset's enrichment builds."""
    service = SonarWebhookService(db)
    return service.get_dataset_pending_scans(dataset_id)


# WebSocket connections store
active_dataset_connections: dict[str, Set[WebSocket]] = {}


@router.websocket("/ws/dataset/{dataset_id}")
async def dataset_scan_websocket(websocket: WebSocket, dataset_id: str):
    """WebSocket for real-time scan updates for a dataset."""
    await websocket.accept()

    # Add to active connections
    if dataset_id not in active_dataset_connections:
        active_dataset_connections[dataset_id] = set()
    active_dataset_connections[dataset_id].add(websocket)

    try:
        while True:
            # Keep connection alive with ping/pong
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        # Remove from active connections
        if dataset_id in active_dataset_connections:
            active_dataset_connections[dataset_id].discard(websocket)


async def broadcast_scan_update(dataset_id: str, message: dict):
    """Broadcast scan update to all connected WebSocket clients for a dataset."""
    if dataset_id in active_dataset_connections:
        for websocket in active_dataset_connections[dataset_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                pass
