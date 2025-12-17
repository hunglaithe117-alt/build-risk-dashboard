"""Dataset validation API endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.dataset_validation import (
    ValidationStatusResponse,
    StartValidationResponse,
    RepoValidationResult,
    ValidationSummaryResponse,
    SaveReposRequest,
    SaveReposResponse,
)
from app.services.dataset_validation_service import DatasetValidationService


router = APIRouter(prefix="/datasets", tags=["dataset-validation"])


@router.post("/{dataset_id}/repos", response_model=SaveReposResponse)
async def save_repos(
    dataset_id: str,
    request: SaveReposRequest,
    db: Database = Depends(get_db),
):
    """Update repository configs from Step 2."""
    service = DatasetValidationService(db)
    result = service.save_repos(dataset_id, request.repos)
    return SaveReposResponse(**result)


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


@router.delete("/{dataset_id}/validation")
async def cancel_validation(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Cancel ongoing validation."""
    service = DatasetValidationService(db)
    return await service.cancel_validation(dataset_id)


@router.get(
    "/{dataset_id}/validation-summary", response_model=ValidationSummaryResponse
)
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
