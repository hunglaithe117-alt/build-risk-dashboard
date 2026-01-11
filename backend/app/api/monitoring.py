"""
Monitoring API - Endpoints for system monitoring and observability.

Endpoints:
- GET /monitoring/system - System stats (Celery, Redis, MongoDB)
- GET /monitoring/audit-logs - Feature extraction audit logs
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
    Export system logs as JSON or CSV (streaming).

    Admin only. Returns up to 10,000 logs for download.
    """
    from fastapi.responses import StreamingResponse

    service = MonitoringService(db)

    content = service.stream_logs_export(format=format, level=level, source=source)

    media_type = "text/csv" if format == "csv" else "application/json"
    filename = f"system_logs.{format}"

    return StreamingResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/metrics")
def get_log_metrics(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (max 7 days)"),
    bucket_minutes: int = Query(
        60, ge=15, le=360, description="Bucket size in minutes"
    ),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """
    Get log metrics aggregated by time bucket for charts.

    Returns time-series data of log counts by level, suitable for
    visualizing error rate trends on the monitoring dashboard.
    """
    service = MonitoringService(db)
    return service.get_log_metrics(hours=hours, bucket_minutes=bucket_minutes)
