import logging
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.repositories.dataset_version import DatasetVersionRepository
from app.services.dataset_service import DatasetService
from app.dtos.dataset_version import (
    CreateVersionRequest,
    VersionResponse,
    VersionListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets/{dataset_id}/versions", tags=["Dataset Versions"])


# --- Helper Functions ---


def _get_sources_from_features(features: List[str]) -> List[str]:
    """Extract unique data sources from feature names."""
    sources = set()
    for feature in features:
        if feature.startswith("git_"):
            sources.add("git")
        elif feature.startswith("gh_"):
            sources.add("github")
        elif feature.startswith("tr_log_"):
            sources.add("build_log")
        elif feature.startswith("tr_"):
            sources.add("repo")
        elif feature.startswith("sonar_"):
            sources.add("sonarqube")
        elif feature.startswith("trivy_"):
            sources.add("trivy")
    return sorted(sources)


def _version_to_response(version: DatasetVersion) -> VersionResponse:
    """Convert entity to response model."""
    return VersionResponse(
        id=str(version.id),
        dataset_id=version.dataset_id,
        version_number=version.version_number,
        name=version.name,
        description=version.description,
        selected_features=version.selected_features,
        selected_sources=version.selected_sources,
        status=(
            version.status.value
            if isinstance(version.status, VersionStatus)
            else version.status
        ),
        total_rows=version.total_rows,
        processed_rows=version.processed_rows,
        enriched_rows=version.enriched_rows,
        failed_rows=version.failed_rows,
        skipped_rows=version.skipped_rows,
        progress_percent=version.progress_percent,
        file_name=version.file_name,
        file_size_bytes=version.file_size_bytes,
        started_at=version.started_at.isoformat() if version.started_at else None,
        completed_at=version.completed_at.isoformat() if version.completed_at else None,
        error_message=version.error_message,
        created_at=version.created_at.isoformat() if version.created_at else "",
    )


# --- Endpoints ---


@router.get("", response_model=VersionListResponse)
async def list_versions(
    dataset_id: str,
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all versions for a dataset."""
    # Verify dataset access
    dataset_service = DatasetService(db)
    dataset = dataset_service.get_dataset(dataset_id, str(current_user["_id"]))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    repo = DatasetVersionRepository(db)
    versions = repo.find_by_dataset(dataset_id, limit=limit)

    return VersionListResponse(
        versions=[_version_to_response(v) for v in versions],
        total=len(versions),
    )


@router.post("", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    dataset_id: str,
    request: CreateVersionRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new version and start enrichment."""
    user_id = str(current_user["_id"])

    # Verify dataset access and get metadata
    dataset_service = DatasetService(db)
    dataset = dataset_service.get_dataset(dataset_id, user_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Check if validation is completed
    if dataset.validation_status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Dataset validation must be completed before creating versions",
        )

    repo = DatasetVersionRepository(db)

    # Check for active version
    active_version = repo.find_active_by_dataset(dataset_id)
    if active_version:
        raise HTTPException(
            status_code=400,
            detail=f"Version v{active_version.version_number} is still processing. Wait for it to complete or cancel it.",
        )

    # Get next version number
    version_number = repo.get_next_version_number(dataset_id)

    # Extract sources from features
    selected_sources = _get_sources_from_features(request.selected_features)

    # Create version entity
    version = DatasetVersion(
        dataset_id=dataset_id,
        user_id=user_id,
        version_number=version_number,
        name=request.name or "",
        description=request.description,
        selected_features=request.selected_features,
        selected_sources=selected_sources,
        total_rows=dataset.rows or 0,
        status=VersionStatus.PENDING,
    )

    # Generate default name if not provided
    if not version.name:
        version.name = version.generate_default_name()

    # Save to database
    version = repo.create(version)

    # Start enrichment task
    from app.tasks.version_enrichment import enrich_version_task

    task = enrich_version_task.delay(str(version.id))
    repo.update_one(str(version.id), {"task_id": task.id})

    logger.info(
        f"Created version {version_number} for dataset {dataset_id} "
        f"with {len(request.selected_features)} features"
    )

    return _version_to_response(version)


@router.get("/{version_id}", response_model=VersionResponse)
async def get_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a specific version."""
    # Verify dataset access
    dataset_service = DatasetService(db)
    dataset = dataset_service.get_dataset(dataset_id, str(current_user["_id"]))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    repo = DatasetVersionRepository(db)
    version = repo.find_by_id(version_id)

    if not version or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Version not found")

    return _version_to_response(version)


@router.get("/{version_id}/download")
async def download_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download the enriched CSV for a version."""
    # Verify dataset access
    dataset_service = DatasetService(db)
    dataset = dataset_service.get_dataset(dataset_id, str(current_user["_id"]))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    repo = DatasetVersionRepository(db)
    version = repo.find_by_id(version_id)

    if not version or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.status != VersionStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Version is not completed. Status: {version.status}",
        )

    if not version.file_path or not os.path.exists(version.file_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    filename = (
        version.file_name or f"enriched_{dataset.name}_v{version.version_number}.csv"
    )

    return FileResponse(
        path=version.file_path,
        filename=filename,
        media_type="text/csv",
    )


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a version and its output file."""
    # Verify dataset access
    dataset_service = DatasetService(db)
    dataset = dataset_service.get_dataset(dataset_id, str(current_user["_id"]))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    repo = DatasetVersionRepository(db)
    version = repo.find_by_id(version_id)

    if not version or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Version not found")

    # Cancel if still processing
    if version.status in (VersionStatus.PENDING, VersionStatus.PROCESSING):
        if version.task_id:
            from app.celery_app import celery_app

            celery_app.control.revoke(version.task_id, terminate=True)

    # Delete output file if exists
    if version.file_path and os.path.exists(version.file_path):
        try:
            os.remove(version.file_path)
        except OSError as e:
            logger.warning(f"Failed to delete file {version.file_path}: {e}")

    # Delete from database
    repo.delete(version_id)

    logger.info(f"Deleted version {version_id} for dataset {dataset_id}")


@router.post("/{version_id}/cancel", response_model=VersionResponse)
async def cancel_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a processing version."""
    # Verify dataset access
    dataset_service = DatasetService(db)
    dataset = dataset_service.get_dataset(dataset_id, str(current_user["_id"]))
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    repo = DatasetVersionRepository(db)
    version = repo.find_by_id(version_id)

    if not version or version.dataset_id != dataset_id:
        raise HTTPException(status_code=404, detail="Version not found")

    if version.status not in (VersionStatus.PENDING, VersionStatus.PROCESSING):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel version with status: {version.status}",
        )

    # Revoke Celery task
    if version.task_id:
        from app.celery_app import celery_app

        celery_app.control.revoke(version.task_id, terminate=True)

    # Mark as cancelled
    repo.mark_cancelled(version_id)
    version.status = VersionStatus.CANCELLED

    logger.info(f"Cancelled version {version_id}")

    return _version_to_response(version)
