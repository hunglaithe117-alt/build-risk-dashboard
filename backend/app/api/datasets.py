from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi import (
    Path as PathParam,
)
from fastapi.exceptions import HTTPException
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    DatasetListResponse,
    DatasetResponse,
)
from app.dtos.dataset import DatasetUpdateRequest
from app.middleware.rbac import Permission, RequirePermission
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("/", response_model=DatasetListResponse, response_model_by_alias=False)
def list_datasets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search by name, file, or tag"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """List datasets for the signed-in user (Admin only)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.list_datasets(user_id, skip=skip, limit=limit, q=q)


@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """Upload a CSV file and create dataset (Admin only)."""
    user_id = str(current_user["_id"])
    upload_fobj = file.file
    try:
        upload_fobj.seek(0)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not prepare file for upload: {str(e)}",
        )

    service = DatasetService(db)
    return service.create_from_upload(
        user_id=user_id,
        filename=file.filename,
        upload_file=upload_fobj,
        name=name,
        description=description,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def get_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """Get dataset details (Admin only)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.get_dataset(dataset_id, user_id)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """Delete a dataset and all associated data (Admin only)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    service.delete_dataset(dataset_id, user_id)
    return None


@router.patch(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def update_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    payload: DatasetUpdateRequest = ...,
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """Update dataset fields (Admin only)."""

    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.update_dataset(
        dataset_id=dataset_id,
        user_id=user_id,
        updates=payload.model_dump(exclude_none=True),
    )


@router.get("/{dataset_id}/builds")
def list_dataset_builds(
    dataset_id: str = PathParam(..., description="Dataset id"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(
        default=None, description="Filter by status: found/not_found/error"
    ),
    q: str | None = Query(default=None, description="Search by repo name, build ID, or commit SHA"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """List builds for a dataset with enriched details from RawBuildRun."""
    service = DatasetService(db)
    user_id = str(current_user["_id"])

    return service.get_dataset_builds(
        dataset_id=dataset_id,
        user_id=user_id,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        q=q,
    )


@router.get("/{dataset_id}/builds/stats")
def get_dataset_builds_stats(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """Get aggregated build stats for charts."""
    service = DatasetService(db)
    user_id = str(current_user["_id"])

    return service.get_dataset_builds_stats(
        dataset_id=dataset_id,
        user_id=user_id,
    )


@router.get("/{dataset_id}/audit-logs/cursor")
def get_dataset_audit_logs_cursor(
    dataset_id: str = PathParam(..., description="Dataset id"),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, description="Cursor from previous page"),
    status: str | None = Query(None, description="Filter by status"),
    version_id: str | None = Query(None, description="Filter by version id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get feature audit logs for a specific dataset with cursor-based pagination.

    Returns logs from feature extraction pipeline for all versions of this dataset.
    """
    from app.services.monitoring_service import MonitoringService

    # Verify dataset access first
    service = DatasetService(db)
    service.get_dataset(dataset_id, str(current_user["_id"]))

    # Get audit logs
    monitoring_service = MonitoringService(db)
    return monitoring_service.get_feature_audit_logs_by_dataset_cursor(
        dataset_id=dataset_id,
        limit=limit,
        cursor=cursor,
        status=status,
        version_id=version_id,
    )


@router.get("/{dataset_id}/audit-logs")
def get_dataset_audit_logs_page(
    dataset_id: str = PathParam(..., description="Dataset id"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status: str | None = Query(None, description="Filter by status"),
    version_id: str | None = Query(None, description="Filter by version id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get feature audit logs for a specific dataset with page-based pagination.
    """
    from app.services.monitoring_service import MonitoringService

    # Verify dataset access first
    service = DatasetService(db)
    service.get_dataset(dataset_id, str(current_user["_id"]))

    # Get audit logs
    monitoring_service = MonitoringService(db)
    return monitoring_service.get_feature_audit_logs_by_dataset_page(
        dataset_id=dataset_id,
        page=page,
        page_size=page_size,
        status=status,
        version_id=version_id,
    )


@router.get("/{dataset_id}/audit-logs/{log_id}")
def get_dataset_audit_log_detail(
    dataset_id: str = PathParam(..., description="Dataset id"),
    log_id: str = PathParam(..., description="Audit log id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get detailed audit log with full node execution results.

    Returns complete node_results with timing and feature extraction details.
    """
    from app.services.monitoring_service import MonitoringService

    # Verify dataset access first
    service = DatasetService(db)
    service.get_dataset(dataset_id, str(current_user["_id"]))

    # Get audit log detail
    monitoring_service = MonitoringService(db)
    result = monitoring_service.get_audit_log_detail(log_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )

    return result
