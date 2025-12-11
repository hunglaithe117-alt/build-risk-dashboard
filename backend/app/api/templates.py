from fastapi import APIRouter, Depends, Path as PathParam
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    DatasetTemplateListResponse,
    DatasetTemplateResponse,
)
from app.services.dataset_template_service import DatasetTemplateService

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get(
    "/",
    response_model=DatasetTemplateListResponse,
    response_model_by_alias=False,
)
def list_templates(
    db: Database = Depends(get_db),
):
    """List all available dataset templates."""
    service = DatasetTemplateService(db)
    return service.list_templates()


@router.get(
    "/by-name/{name}",
    response_model=DatasetTemplateResponse,
    response_model_by_alias=False,
)
def get_template_by_name(
    name: str = PathParam(..., description="Template name"),
    db: Database = Depends(get_db),
):
    """Get a template by its name."""
    service = DatasetTemplateService(db)
    return service.get_template_by_name(name)
