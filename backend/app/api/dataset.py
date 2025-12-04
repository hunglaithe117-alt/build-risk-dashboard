"""
Dataset Builder API.

Endpoints for the Custom Dataset Builder feature.
Users can:
1. Browse available features
2. Preview dependency resolution
3. Create dataset extraction jobs
4. Monitor job progress
5. Download completed datasets
"""

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import FileResponse
from pymongo.database import Database

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.services.dataset_service import DatasetService
from app.models.entities.dataset_job import DatasetJobStatus
from app.dtos.dataset import (
    AvailableFeaturesResponse,
    DatasetJobCreateRequest,
    DatasetJobCreatedResponse,
    DatasetJobListResponse,
    DatasetJobResponse,
    ResolvedDependenciesResponse,
)

router = APIRouter(prefix="/datasets", tags=["Custom Dataset Builder"])


# ====================
# Feature Discovery
# ====================


@router.get(
    "/features",
    response_model=AvailableFeaturesResponse,
    summary="List Available Features",
    description="Get all available features grouped by category for selection.",
)
def list_available_features(
    ml_only: bool = Query(default=False, description="Only show ML features"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all available features that can be extracted."""
    service = DatasetService(db)
    return service.get_available_features(ml_only=ml_only)


@router.post(
    "/features/resolve",
    response_model=ResolvedDependenciesResponse,
    summary="Resolve Feature Dependencies",
    description="Preview what will be extracted based on selected features.",
)
def resolve_feature_dependencies(
    feature_ids: List[str] = Query(
        ...,
        description="List of feature IDs to resolve",
        example=["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"],
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Resolve dependencies for selected features.

    Returns:
    - All features that will be extracted (including dependencies)
    - Required extractor nodes
    - Resource requirements (clone, log collection)
    """
    service = DatasetService(db)
    try:
        return service.resolve_dependencies(feature_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ====================
# Job Management
# ====================


@router.post(
    "/jobs",
    response_model=DatasetJobCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Dataset Job",
    description="Create a new dataset extraction job.",
)
def create_dataset_job(
    request: DatasetJobCreateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new dataset extraction job.

    The job will:
    1. Clone/access the repository
    2. Collect workflow runs (up to max_builds)
    3. Extract selected features (with dependencies)
    4. Export to CSV file

    Returns job ID for tracking progress.
    """
    user_id = str(current_user["_id"])
    service = DatasetService(db)

    try:
        return service.create_job(user_id, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/jobs",
    response_model=DatasetJobListResponse,
    summary="List Dataset Jobs",
    description="List all dataset jobs for the current user.",
)
def list_dataset_jobs(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: pending, processing, completed, failed",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List user's dataset jobs with pagination."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)

    status_enum = None
    if status_filter:
        try:
            status_enum = DatasetJobStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status_filter}. Valid values: {[s.value for s in DatasetJobStatus]}",
            )

    return service.list_jobs(user_id, page, page_size, status_enum)


@router.get(
    "/jobs/{job_id}",
    response_model=DatasetJobResponse,
    summary="Get Job Details",
    description="Get details and progress of a dataset job.",
)
def get_dataset_job(
    job_id: str = Path(..., description="Dataset job ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get job details including progress."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)

    try:
        return service.get_job(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=DatasetJobResponse,
    summary="Cancel Job",
    description="Cancel a pending or processing job.",
)
def cancel_dataset_job(
    job_id: str = Path(..., description="Dataset job ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a running job."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)

    try:
        return service.cancel_job(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Job",
    description="Delete a job and its output file.",
)
def delete_dataset_job(
    job_id: str = Path(..., description="Dataset job ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a job and clean up its resources."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)

    try:
        service.delete_job(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get(
    "/jobs/{job_id}/samples",
    summary="Get Job Samples",
    description="Get extracted samples for a job (for preview).",
)
def get_job_samples(
    job_id: str = Path(..., description="Dataset job ID"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status (completed, failed, pending)",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get samples (rows) for a dataset job.

    Useful for:
    - Previewing data before download
    - Debugging extraction issues
    - Viewing partial results while job is processing
    """
    from app.repositories.dataset_sample import DatasetSampleRepository

    user_id = str(current_user["_id"])
    service = DatasetService(db)

    # Verify job exists and user has access
    try:
        job = service.get_job(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Get samples
    sample_repo = DatasetSampleRepository(db)
    skip = (page - 1) * page_size
    samples, total = sample_repo.find_by_job_id(
        job_id,
        status=status_filter,
        skip=skip,
        limit=page_size,
    )

    # Convert to response format
    items = []
    for sample in samples:
        item = {
            "id": str(sample.id),
            "workflow_run_id": sample.workflow_run_id,
            "commit_sha": sample.commit_sha,
            "build_number": sample.build_number,
            "build_status": sample.build_status,
            "status": sample.status,
            "error_message": sample.error_message,
            "features": sample.features,
            "extracted_at": (
                sample.extracted_at.isoformat() if sample.extracted_at else None
            ),
        }
        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get(
    "/jobs/{job_id}/preview",
    summary="Preview Dataset CSV",
    description="Preview the first N rows of the dataset without downloading.",
)
def preview_dataset(
    job_id: str = Path(..., description="Dataset job ID"),
    rows: int = Query(
        default=10, ge=1, le=100, description="Number of rows to preview"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Preview the dataset CSV content.

    Returns the first N rows of the completed dataset for quick inspection.
    """
    from bson import ObjectId
    from app.repositories.dataset_job import DatasetJobRepository
    from app.repositories.dataset_sample import DatasetSampleRepository

    user_id = str(current_user["_id"])
    job_repo = DatasetJobRepository(db)

    # Get job entity directly
    job = job_repo.find_by_id(ObjectId(job_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ownership
    if str(job.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get completed samples
    sample_repo = DatasetSampleRepository(db)
    samples = sample_repo.get_completed_samples(job_id, limit=rows)

    if not samples:
        return {
            "columns": [],
            "rows": [],
            "total_rows": 0,
            "preview_rows": 0,
        }

    # Build columns - only features
    columns = sorted(job.resolved_features)

    # Build rows - only features
    preview_rows = []
    for sample in samples:
        row = {}

        for feature in sorted(job.resolved_features):
            row[feature] = sample.features.get(feature)

        preview_rows.append(row)

    # Get total count
    stats = sample_repo.get_job_stats(job_id)

    return {
        "columns": columns,
        "rows": preview_rows,
        "total_rows": stats["completed"],
        "preview_rows": len(preview_rows),
    }


# ====================
# Download
# ====================


@router.get(
    "/jobs/{job_id}/download",
    summary="Download Dataset",
    description="Download the completed dataset CSV file.",
)
def download_dataset(
    job_id: str = Path(..., description="Dataset job ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download the completed dataset CSV."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    job_repo = service.job_repo

    try:
        job = service.get_job(job_id, user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if job.status != DatasetJobStatus.COMPLETED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed. Current status: {job.status}",
        )

    if not job.output_file_path or not os.path.exists(job.output_file_path):
        raise HTTPException(
            status_code=404, detail="Output file not found. It may have been deleted."
        )

    # Increment download count
    job_repo.increment_download_count(job_id)

    # Generate filename
    # Extract repo name from URL
    repo_name = job.repo_url.rstrip("/").split("/")[-1]
    filename = f"{repo_name}_dataset_{job_id[:8]}.csv"

    return FileResponse(
        path=job.output_file_path,
        media_type="text/csv",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ====================
# Statistics
# ====================


@router.get(
    "/stats",
    summary="Get Dataset Stats",
    description="Get statistics about user's dataset jobs.",
)
def get_dataset_stats(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get user's dataset statistics."""
    from bson import ObjectId

    user_id = str(current_user["_id"])

    pipeline = [
        {"$match": {"user_id": ObjectId(user_id)}},
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_rows": {"$sum": "$output_row_count"},
                "total_downloads": {"$sum": "$download_count"},
            }
        },
    ]

    results = list(db.dataset_jobs.aggregate(pipeline))

    stats = {
        "total_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0,
        "pending_jobs": 0,
        "processing_jobs": 0,
        "total_rows_generated": 0,
        "total_downloads": 0,
    }

    for r in results:
        count = r["count"]
        stats["total_jobs"] += count

        status_val = r["_id"]
        if status_val == DatasetJobStatus.COMPLETED.value:
            stats["completed_jobs"] = count
            stats["total_rows_generated"] = r.get("total_rows") or 0
            stats["total_downloads"] = r.get("total_downloads") or 0
        elif status_val == DatasetJobStatus.FAILED.value:
            stats["failed_jobs"] = count
        elif status_val == DatasetJobStatus.PENDING.value:
            stats["pending_jobs"] = count
        elif status_val == DatasetJobStatus.PROCESSING.value:
            stats["processing_jobs"] = count

    return stats
