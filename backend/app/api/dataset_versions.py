import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.database.mongo import get_db
from app.dtos.dataset_version import (
    CreateVersionRequest,
    VersionListResponse,
    VersionResponse,
)
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.middleware.rbac import Permission, RequirePermission
from app.services.dataset_version_service import DatasetVersionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets/{dataset_id}/versions", tags=["Dataset Versions"])


def _to_response(version: DatasetVersion) -> VersionResponse:
    return VersionResponse(
        id=str(version.id),
        dataset_id=version.dataset_id,
        version_number=version.version_number,
        name=version.name,
        description=version.description,
        selected_features=version.selected_features,
        status=(
            version.status.value if isinstance(version.status, VersionStatus) else version.status
        ),
        total_rows=version.total_rows,
        processed_rows=version.processed_rows,
        enriched_rows=version.enriched_rows,
        failed_rows=version.failed_rows,
        skipped_rows=version.skipped_rows,
        progress_percent=version.progress_percent,
        started_at=version.started_at.isoformat() if version.started_at else None,
        completed_at=version.completed_at.isoformat() if version.completed_at else None,
        error_message=version.error_message,
        created_at=version.created_at.isoformat() if version.created_at else "",
    )


@router.get("", response_model=VersionListResponse)
async def list_versions(
    dataset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    service = DatasetVersionService(db)
    versions, total = service.list_versions(
        dataset_id, str(current_user["_id"]), skip=skip, limit=limit
    )
    return VersionListResponse(
        versions=[_to_response(v) for v in versions],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    dataset_id: str,
    request: CreateVersionRequest,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    service = DatasetVersionService(db)
    version = service.create_version(
        dataset_id=dataset_id,
        user_id=str(current_user["_id"]),
        selected_features=request.selected_features,
        feature_configs=request.feature_configs,
        scan_metrics=request.scan_metrics,
        scan_config=request.scan_config,
        name=request.name,
        description=request.description,
    )
    return _to_response(version)


@router.get("/{version_id}", response_model=VersionResponse)
async def get_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    service = DatasetVersionService(db)
    version = service.get_version(dataset_id, version_id, str(current_user["_id"]))
    return _to_response(version)


@router.get("/{version_id}/export")
async def export_version(
    dataset_id: str,
    version_id: str,
    format: str = Query("csv", regex="^(csv|json|parquet)$"),
    features: Optional[List[str]] = Query(None),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.EXPORT_DATA)),
):
    """
    Export version data in CSV, JSON, or Parquet format.

    - **format**: Export format (csv, json, parquet)
    - **features**: Optional list of features to include (defaults to all selected features)
    """
    service = DatasetVersionService(db)
    result = service.export_version(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        format=format,
        features=features,
    )

    return StreamingResponse(
        result.content_generator,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/{version_id}/preview")
async def preview_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """Get preview of exportable data for a version."""
    service = DatasetVersionService(db)
    return service.get_export_preview(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.get("/{version_id}/data")
async def get_version_data(
    dataset_id: str,
    version_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get paginated version data with column statistics.

    Returns:
    - version: Metadata about the version
    - data: Paginated rows with features
    - column_stats: Statistics for each feature column (only on page 1)
    """
    service = DatasetVersionService(db)
    return service.get_version_data(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        page=page,
        page_size=page_size,
    )


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    service = DatasetVersionService(db)
    service.delete_version(dataset_id, version_id, str(current_user["_id"]))


@router.post("/{version_id}/cancel", response_model=VersionResponse)
async def cancel_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    service = DatasetVersionService(db)
    version = service.cancel_version(dataset_id, version_id, str(current_user["_id"]))
    return _to_response(version)


@router.get("/{version_id}/scan-status")
async def get_scan_status(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get scan status summary for a version.

    Returns counts of builds with sonar/trivy features.
    """
    service = DatasetVersionService(db)
    return service.get_scan_status(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.post("/{version_id}/retry-scan")
async def retry_version_scans(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.START_SCANS)),
):
    """
    Retry failed scans for a version.

    Re-dispatches scans for commits that had scan failures.
    """
    service = DatasetVersionService(db)
    return service.retry_scans(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.get("/{version_id}/commit-scans")
async def get_commit_scans(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get detailed commit scan status for a version.

    Returns separate lists for Trivy and SonarQube scans with status per commit.
    """
    service = DatasetVersionService(db)
    return service.get_commit_scans(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.post("/{version_id}/commits/{commit_sha}/retry/{tool_type}")
async def retry_commit_scan(
    dataset_id: str,
    version_id: str,
    commit_sha: str,
    tool_type: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.START_SCANS)),
):
    """
    Retry a specific commit scan for a tool (trivy or sonarqube).
    """
    service = DatasetVersionService(db)
    return service.retry_commit_scan(
        dataset_id=dataset_id,
        version_id=version_id,
        commit_sha=commit_sha,
        tool_type=tool_type,
        user_id=str(current_user["_id"]),
    )
