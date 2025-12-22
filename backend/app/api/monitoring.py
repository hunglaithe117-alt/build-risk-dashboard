"""
Monitoring API - Endpoints for system monitoring and observability.

Endpoints:
- GET /monitoring/system - System stats (Celery, Redis, MongoDB)
- GET /monitoring/pipeline-runs - Recent pipeline runs
- GET /monitoring/jobs - Active background jobs
- GET /monitoring/queues - Celery queue details
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.database.mongo import get_db
from app.middleware.rbac import Permission, RequirePermission
from app.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/system")
def get_system_stats(
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get comprehensive system statistics.

    Returns stats for:
    - Celery workers and queues
    - Redis server
    - MongoDB server
    """
    service = MonitoringService(db)
    return service.get_system_stats()


@router.get("/pipeline-runs")
def get_pipeline_runs(
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get recent pipeline runs with pagination.

    Shows Hamilton pipeline execution history with timing and status.
    """
    service = MonitoringService(db)
    return service.get_pipeline_runs(limit=limit, skip=skip, status=status)


@router.get("/pipeline-runs/cursor")
def get_pipeline_runs_cursor(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Cursor from previous page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get pipeline runs with cursor-based pagination for infinite scroll.

    Returns runs with enriched repository and build information.
    """
    service = MonitoringService(db)
    return service.get_pipeline_runs_cursor(limit=limit, cursor=cursor, status=status)


@router.get("/jobs")
def get_background_jobs(
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get active background jobs overview.

    Returns:
    - Active export jobs
    - Active scans (SonarQube, Trivy)
    - Active enrichment jobs
    """
    service = MonitoringService(db)
    return service.get_background_jobs()


@router.get("/queues")
def get_queue_stats(
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get detailed Celery queue statistics.

    Shows message counts for each queue.
    """
    service = MonitoringService(db)
    stats = service.get_system_stats()
    return {
        "queues": stats.get("celery", {}).get("queues", {}),
        "workers": stats.get("celery", {}).get("workers", []),
    }


@router.get("/logs")
def get_system_logs(
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    level: Optional[str] = Query(
        None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"
    ),
    source: Optional[str] = Query(None, description="Filter by source/component"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get system logs with pagination and filtering.

    Admin only. Returns logs stored in MongoDB from the application.
    """
    service = MonitoringService(db)
    return service.get_system_logs(limit=limit, skip=skip, level=level, source=source)


@router.get("/logs/export")
def export_system_logs(
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    format: str = Query("json", description="Export format: json or csv"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Export system logs as JSON or CSV.

    Admin only. Returns up to 10,000 logs for download.
    """
    import csv
    import io
    import json

    from fastapi.responses import StreamingResponse

    service = MonitoringService(db)
    logs = service.get_logs_for_export(level=level, source=source)

    if format == "csv":
        output = io.StringIO()
        if logs:
            writer = csv.DictWriter(
                output,
                fieldnames=["timestamp", "level", "source", "message", "details"],
            )
            writer.writeheader()
            for log in logs:
                log["details"] = json.dumps(log.get("details")) if log.get("details") else ""
                writer.writerow(log)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=system_logs.csv"},
        )
    else:
        return StreamingResponse(
            iter([json.dumps(logs, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=system_logs.json"},
        )
