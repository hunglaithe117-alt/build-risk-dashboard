"""Dataset validation API endpoints."""

from fastapi import APIRouter, Depends, Query
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.dataset_validation import (
    RepoValidationResult,
    StartValidationResponse,
    ValidationStatusResponse,
    ValidationSummaryResponse,
)
from app.services.dataset_validation_service import DatasetValidationService

router = APIRouter(prefix="/datasets", tags=["dataset-validation"])


@router.post("/{dataset_id}/validate", response_model=StartValidationResponse)
async def start_validation(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Start async validation of builds in a dataset."""
    service = DatasetValidationService(db)
    result = await service.start_validation(dataset_id)
    return StartValidationResponse(**result)


@router.get("/{dataset_id}/validation-status", response_model=ValidationStatusResponse)
async def get_validation_status(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Get current validation progress and status."""
    service = DatasetValidationService(db)
    result = service.get_validation_status(dataset_id)
    return ValidationStatusResponse(**result)


@router.get("/{dataset_id}/validation-summary", response_model=ValidationSummaryResponse)
async def get_validation_summary(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Get detailed validation summary including repo breakdown."""
    service = DatasetValidationService(db)
    result = service.get_validation_summary(dataset_id)
    return ValidationSummaryResponse(
        dataset_id=result["dataset_id"],
        status=result["status"],
        stats=result["stats"],
        repos=[RepoValidationResult(**r) for r in result["repos"]],
    )


@router.get("/{dataset_id}/repos")
async def list_dataset_repos(
    dataset_id: str,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    db: Database = Depends(get_db),
):
    """List repositories in a dataset (paginated)."""
    service = DatasetValidationService(db)
    return service.get_dataset_repos(
        dataset_id,
        skip=skip,
        limit=limit,
        search=q,
    )


@router.post("/{dataset_id}/reset-validation")
async def reset_validation(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Reset validation state and delete build records to allow re-validation."""
    service = DatasetValidationService(db)
    return await service.reset_validation(dataset_id)


@router.post("/{dataset_id}/reset-step2")
async def reset_step2(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Reset Step 2 data - delete repos and build records when going back to Step 1."""
    service = DatasetValidationService(db)
    return await service.reset_step2(dataset_id)
