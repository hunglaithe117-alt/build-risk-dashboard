import logging

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.services.dataset_version_service import DatasetVersionService
from app.dtos.dataset_version import (
    CreateVersionRequest,
    VersionResponse,
    VersionListResponse,
)

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


@router.get("", response_model=VersionListResponse)
async def list_versions(
    dataset_id: str,
    limit: int = Query(50, ge=1, le=100),
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetVersionService(db)
    versions = service.list_versions(dataset_id, str(current_user["_id"]), limit)
    return VersionListResponse(
        versions=[_to_response(v) for v in versions],
        total=len(versions),
    )


@router.post("", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    dataset_id: str,
    request: CreateVersionRequest,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetVersionService(db)
    version = service.create_version(
        dataset_id=dataset_id,
        user_id=str(current_user["_id"]),
        selected_features=request.selected_features,
        name=request.name,
        description=request.description,
    )
    return _to_response(version)


@router.get("/{version_id}", response_model=VersionResponse)
async def get_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetVersionService(db)
    version = service.get_version(dataset_id, version_id, str(current_user["_id"]))
    return _to_response(version)


@router.get("/{version_id}/download")
async def download_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetVersionService(db)
    result = service.download_as_csv(dataset_id, version_id, str(current_user["_id"]))
    return StreamingResponse(
        iter([result.content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetVersionService(db)
    service.delete_version(dataset_id, version_id, str(current_user["_id"]))


@router.post("/{version_id}/cancel", response_model=VersionResponse)
async def cancel_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = DatasetVersionService(db)
    version = service.cancel_version(dataset_id, version_id, str(current_user["_id"]))
    return _to_response(version)
