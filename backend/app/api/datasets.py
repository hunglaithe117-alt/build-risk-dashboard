from fastapi import (
    APIRouter,
    Body,
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
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdateRequest,
)
from app.middleware.auth import get_current_user
from app.middleware.require_dataset_manager import require_dataset_manager
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("/", response_model=DatasetListResponse, response_model_by_alias=False)
def list_datasets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search by name, file, or tag"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List datasets for the signed-in user."""
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")
    service = DatasetService(db)
    return service.list_datasets(user_id, role=role, skip=skip, limit=limit, q=q)


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
    current_user: dict = Depends(require_dataset_manager),
):
    """Upload a CSV file and create dataset (Admin and Guest)."""
    user_id = str(current_user["_id"])
    upload_fobj = file.file
    try:
        upload_fobj.seek(0)
    except Exception:
        pass

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
    current_user: dict = Depends(get_current_user),
):
    """Get dataset details."""
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")
    service = DatasetService(db)
    return service.get_dataset(dataset_id, user_id, role=role)


@router.patch(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def update_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    payload: DatasetUpdateRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_dataset_manager),
):
    """Update dataset metadata (Admin and Guest)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.update_dataset(dataset_id, user_id, payload)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_dataset_manager),
):
    """Delete a dataset and all associated data (Admin and Guest)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    service.delete_dataset(dataset_id, user_id)
    return None


@router.get("/{dataset_id}/builds")
def list_dataset_builds(
    dataset_id: str = PathParam(..., description="Dataset id"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(
        default=None, description="Filter by status: found/not_found/error"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List builds for a dataset with enriched details from RawBuildRun."""
    service = DatasetService(db)
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")

    return service.get_dataset_builds(
        dataset_id=dataset_id,
        user_id=user_id,
        role=role,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
    )


@router.get("/{dataset_id}/builds/stats")
def get_dataset_builds_stats(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get aggregated build stats for charts."""
    service = DatasetService(db)
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")

    return service.get_dataset_builds_stats(
        dataset_id=dataset_id,
        user_id=user_id,
        role=role,
    )
