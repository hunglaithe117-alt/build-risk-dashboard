"""
Export API - Endpoints for exporting build data.

Endpoints:
- GET /export/repos/{repo_id} - Stream export for small datasets
- POST /export/repos/{repo_id}/async - Create background export job
- GET /export/jobs/{job_id} - Get job status
- GET /export/jobs/{job_id}/download - Download completed export
- GET /export/repos/{repo_id}/jobs - List export jobs
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pymongo.database import Database

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.export_service import ExportService
from app.tasks.export import run_export_job

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/repos/{repo_id}")
def export_builds(
    repo_id: str = Path(..., description="Repository ID"),
    format: str = Query(default="csv", regex="^(csv|json)$"),
    features: Optional[str] = Query(
        default=None, description="Comma-separated feature names to include"
    ),
    start_date: Optional[datetime] = Query(
        default=None, description="Filter builds created on or after this date"
    ),
    end_date: Optional[datetime] = Query(
        default=None, description="Filter builds created on or before this date"
    ),
    build_status: Optional[str] = Query(
        default=None, description="Filter by build status (e.g., success, failure)"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Export builds as CSV or JSON.

    For small datasets (< 1000 rows), streams directly.
    For large datasets, returns 413 with recommendation to use async endpoint.

    Returns:
        StreamingResponse with CSV or JSON data

    Raises:
        413: Dataset too large, use async export instead
    """
    service = ExportService(db)
    feature_list = features.split(",") if features else None

    # Check if too large for streaming
    if service.should_use_background_job(repo_id, start_date, end_date, build_status):
        count = service.estimate_row_count(repo_id, start_date, end_date, build_status)
        raise HTTPException(
            status_code=413,
            detail={
                "message": "Dataset too large for streaming. Use async export.",
                "count": count,
                "threshold": 1000,
                "async_endpoint": f"/api/export/repos/{repo_id}/async",
            },
        )

    content_type = "text/csv" if format == "csv" else "application/json"
    extension = format

    return StreamingResponse(
        service.stream_export(
            repo_id,
            format=format,
            features=feature_list,
            start_date=start_date,
            end_date=end_date,
            build_status=build_status,
        ),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{repo_id}_builds.{extension}"'
        },
    )


@router.post("/repos/{repo_id}/async")
def create_async_export(
    repo_id: str = Path(..., description="Repository ID"),
    format: str = Query(default="csv", regex="^(csv|json)$"),
    features: Optional[str] = Query(
        default=None, description="Comma-separated feature names to include"
    ),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    build_status: Optional[str] = Query(default=None),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create an async export job for large datasets.

    The export will be processed in the background. Poll the status
    endpoint to check progress, then download when complete.

    Returns:
        job_id: ID to track the export job
        status: "pending"
        poll_url: URL to check job status
    """
    service = ExportService(db)
    user_id = str(current_user["_id"])
    feature_list = features.split(",") if features else None

    # Estimate row count
    count = service.estimate_row_count(repo_id, start_date, end_date, build_status)

    job = service.create_export_job(
        repo_id=repo_id,
        user_id=user_id,
        format=format,
        features=feature_list,
        start_date=start_date,
        end_date=end_date,
        build_status=build_status,
    )

    # Queue background task
    run_export_job.delay(str(job.id))

    return {
        "job_id": str(job.id),
        "status": "pending",
        "estimated_rows": count,
        "format": format,
        "poll_url": f"/api/export/jobs/{job.id}",
        "message": "Export job created. Poll the status endpoint for progress.",
    }


@router.get("/jobs/{job_id}")
def get_export_job_status(
    job_id: str = Path(..., description="Export job ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get status of an export job.

    Returns progress information and download URL when complete.
    """
    service = ExportService(db)
    job = service.job_repo.find_by_id(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    # Calculate progress percentage
    progress = 0.0
    if job.total_rows > 0:
        progress = round(job.processed_rows / job.total_rows * 100, 1)

    result = {
        "job_id": str(job.id),
        "status": job.status,
        "format": job.format,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows,
        "progress_percent": progress,
        "created_at": job.created_at,
    }

    if job.status == "completed":
        result["file_size"] = job.file_size
        result["file_size_mb"] = (
            round(job.file_size / (1024 * 1024), 2) if job.file_size else 0
        )
        result["completed_at"] = job.completed_at
        result["download_url"] = f"/api/export/jobs/{job_id}/download"

    if job.status == "failed":
        result["error_message"] = job.error_message

    return result


@router.get("/jobs/{job_id}/download")
def download_export(
    job_id: str = Path(..., description="Export job ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Download completed export file.

    Returns the CSV or JSON file as a download.

    Raises:
        404: Export file not found or job not completed
    """
    service = ExportService(db)

    # Check job exists and is completed
    job = service.job_repo.find_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=400, detail=f"Export not ready. Current status: {job.status}"
        )

    # Get file path
    file_path = service.get_export_file_path(job_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Export file not found")

    content_type = "text/csv" if job.format == "csv" else "application/json"

    return FileResponse(
        file_path,
        media_type=content_type,
        filename=file_path.name,
    )


@router.get("/repos/{repo_id}/jobs")
def list_export_jobs(
    repo_id: str = Path(..., description="Repository ID"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List export jobs for a repository.

    Returns recent export jobs with status and download links.
    """
    service = ExportService(db)
    jobs = service.job_repo.list_by_repo(repo_id, limit)

    return {
        "items": [
            {
                "job_id": str(j.id),
                "status": j.status,
                "format": j.format,
                "total_rows": j.total_rows,
                "file_size": j.file_size,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
                "download_url": (
                    f"/api/export/jobs/{j.id}/download"
                    if j.status == "completed"
                    else None
                ),
            }
            for j in jobs
        ],
        "count": len(jobs),
    }


@router.get("/repos/{repo_id}/preview")
def preview_export(
    repo_id: str = Path(..., description="Repository ID"),
    features: Optional[str] = Query(default=None),
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    build_status: Optional[str] = Query(default=None),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Preview export without downloading.

    Returns count, sample rows, and available features.
    """
    service = ExportService(db)

    count = service.estimate_row_count(repo_id, start_date, end_date, build_status)
    use_async = service.should_use_background_job(
        repo_id, start_date, end_date, build_status
    )

    # Get sample rows (first 5)
    query = service._build_query(repo_id, start_date, end_date, build_status)
    sample_docs = list(
        service.db.model_builds.find(query).sort("created_at", 1).limit(5)
    )

    feature_list = features.split(",") if features else None
    sample_rows = [service._format_row(doc, feature_list) for doc in sample_docs]

    # Get available features
    available_features = list(
        service._get_all_feature_keys(repo_id, start_date, end_date, build_status)
    )

    return {
        "total_rows": count,
        "use_async_recommended": use_async,
        "async_threshold": 1000,
        "sample_rows": sample_rows,
        "available_features": sorted(available_features),
        "feature_count": len(available_features),
    }
