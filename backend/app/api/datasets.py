"""Dataset API - manage uploaded CSV projects for enrichment."""

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
    DatasetTemplateListResponse,
    DatasetUpdateRequest,
)
from app.middleware.auth import get_current_user
from app.services.dataset_service import DatasetService
from app.services.dataset_template_service import DatasetTemplateService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get(
    "/templates",
    response_model=DatasetTemplateListResponse,
    response_model_by_alias=False,
)
def list_dataset_templates(
    db: Database = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    service = DatasetTemplateService(db)
    return service.list_templates()


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
    service = DatasetService(db)
    return service.list_datasets(user_id, skip=skip, limit=limit, q=q)


@router.post(
    "/", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED, response_model_by_alias=False
)
def create_dataset(
    payload: DatasetCreateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a dataset record (metadata only)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.create_dataset(user_id, payload)


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
    tags: list[str] = Form(default=[]),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload a CSV dataset and persist metadata."""
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
        tags=tags,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def get_dataset(
    dataset_id: str = Path(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get dataset details."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.get_dataset(dataset_id, user_id)


@router.patch(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def update_dataset(
    dataset_id: str = Path(..., description="Dataset id (Mongo ObjectId)"),
    payload: DatasetUpdateRequest = ...,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update mappings, tags, or feature selections for a dataset."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.update_dataset(dataset_id, user_id, payload)


@router.post(
    "/{dataset_id}/apply-template/{template_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def apply_template_to_dataset(
    dataset_id: str = Path(..., description="Dataset id (Mongo ObjectId)"),
    template_id: str = Path(..., description="Dataset template id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Apply a dataset template to a dataset, updating selected features."""
    user_id = str(current_user["_id"])
    service = DatasetTemplateService(db)
    return service.apply_template(dataset_id, template_id, user_id)
