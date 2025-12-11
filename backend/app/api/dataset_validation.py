from typing import List, Optional
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends
from pymongo.database import Database

from pydantic import BaseModel, Field

from app.database.mongo import get_db
from app.core.redis import get_redis
from app.tasks.dataset_validation import validate_dataset_task
from app.entities import ValidationStats, CIProvider
from app.entities.enrichment_repository import (
    EnrichmentRepository,
    RepoValidationStatus,
)


router = APIRouter(prefix="/datasets", tags=["dataset-validation"])


class ValidationStatusResponse(BaseModel):
    dataset_id: str
    status: str
    progress: int = 0
    task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    stats: Optional[ValidationStats] = None


class StartValidationResponse(BaseModel):
    task_id: str
    message: str


class RepoValidationResult(BaseModel):
    id: str
    full_name: str
    validation_status: str
    validation_error: Optional[str] = None
    default_branch: Optional[str] = None
    is_private: bool = False
    builds_found: Optional[int] = None
    builds_not_found: Optional[int] = None


class ValidationSummaryResponse(BaseModel):
    dataset_id: str
    status: str
    stats: ValidationStats
    repos: list[RepoValidationResult] = Field(default_factory=list)


# Request model for saving repos from Step 2
class RepoConfigRequest(BaseModel):
    full_name: str
    ci_provider: str = "github_actions"
    source_languages: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)
    validation_status: str = "valid"


class SaveReposRequest(BaseModel):
    repos: List[RepoConfigRequest]


class SaveReposResponse(BaseModel):
    saved: int
    message: str


@router.post("/{dataset_id}/repos", response_model=SaveReposResponse)
async def save_repos(
    dataset_id: str,
    request: SaveReposRequest,
    db: Database = Depends(get_db),
):
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    saved_count = 0
    for repo_config in request.repos:
        # Skip invalid repos
        if repo_config.validation_status not in ("valid",):
            continue

        # Check if repo already exists
        existing = db.enrichment_repositories.find_one(
            {
                "dataset_id": ObjectId(dataset_id),
                "full_name": repo_config.full_name,
            }
        )

        if existing:
            # Update existing
            db.enrichment_repositories.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "ci_provider": repo_config.ci_provider,
                        "source_languages": repo_config.source_languages,
                        "test_frameworks": repo_config.test_frameworks,
                        "validation_status": RepoValidationStatus.VALID.value,
                        "validated_at": datetime.utcnow(),
                    }
                },
            )
        else:
            enrichment_repo = EnrichmentRepository(
                dataset_id=ObjectId(dataset_id),
                full_name=repo_config.full_name,
                ci_provider=CIProvider(repo_config.ci_provider),
                source_languages=repo_config.source_languages,
                test_frameworks=repo_config.test_frameworks,
                validation_status=RepoValidationStatus.VALID,
                validated_at=datetime.utcnow(),
            )
            db.enrichment_repositories.insert_one(enrichment_repo.to_mongo())
        saved_count += 1

    return SaveReposResponse(
        saved=saved_count, message=f"Saved {saved_count} repositories"
    )


@router.post("/{dataset_id}/validate", response_model=StartValidationResponse)
async def start_validation(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Start async validation of builds in a dataset."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset.get("validation_status") == "validating":
        raise HTTPException(status_code=400, detail="Validation is already in progress")

    mapped_fields = dataset.get("mapped_fields", {})
    if not mapped_fields.get("build_id") or not mapped_fields.get("repo_name"):
        raise HTTPException(
            status_code=400,
            detail="Dataset mapping not configured. Please map build_id and repo_name columns.",
        )

    # Check at least one repo exists
    repo_count = db.enrichment_repositories.count_documents(
        {"dataset_id": ObjectId(dataset_id)}
    )
    if repo_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No validated repositories found. Please complete Step 2 first.",
        )

    task = validate_dataset_task.delay(dataset_id)
    return StartValidationResponse(task_id=task.id, message="Validation started")


@router.get("/{dataset_id}/validation-status", response_model=ValidationStatusResponse)
async def get_validation_status(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Get current validation progress and status."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    stats = None
    if dataset.get("validation_stats"):
        stats = ValidationStats(**dataset["validation_stats"])

    return ValidationStatusResponse(
        dataset_id=dataset_id,
        status=dataset.get("validation_status", "pending"),
        progress=dataset.get("validation_progress", 0),
        task_id=dataset.get("validation_task_id"),
        started_at=dataset.get("validation_started_at"),
        completed_at=dataset.get("validation_completed_at"),
        error=dataset.get("validation_error"),
        stats=stats,
    )


@router.delete("/{dataset_id}/validation")
async def cancel_validation(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Cancel ongoing validation."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset.get("validation_status") != "validating":
        raise HTTPException(status_code=400, detail="No validation in progress")

    redis = await get_redis()
    await redis.set(
        f"dataset_validation:{dataset_id}:cancelled",
        "1",
        ex=3600,
    )

    return {"message": "Cancellation requested"}


@router.get(
    "/{dataset_id}/validation-summary", response_model=ValidationSummaryResponse
)
async def get_validation_summary(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Get detailed validation summary including repo breakdown."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    validation_status = dataset.get("validation_status", "pending")
    if validation_status not in ("completed", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Validation not completed. Current status: {validation_status}",
        )

    stats_dict = dataset.get("validation_stats", {})
    stats = ValidationStats(**stats_dict)

    repos_cursor = db.enrichment_repositories.find({"dataset_id": ObjectId(dataset_id)})
    repos = []
    for repo_doc in repos_cursor:
        repos.append(
            RepoValidationResult(
                id=str(repo_doc["_id"]),
                full_name=repo_doc["full_name"],
                validation_status=repo_doc.get("validation_status", "pending"),
                validation_error=repo_doc.get("validation_error"),
                default_branch=repo_doc.get("default_branch"),
                is_private=repo_doc.get("is_private", False),
                builds_found=repo_doc.get("builds_found"),
                builds_not_found=repo_doc.get("builds_not_found"),
            )
        )

    return ValidationSummaryResponse(
        dataset_id=dataset_id,
        status=validation_status,
        stats=stats,
        repos=repos,
    )


@router.post("/{dataset_id}/reset-validation")
async def reset_validation(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Reset validation state and delete build records to allow re-validation."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Cancel any running task
    redis = await get_redis()
    await redis.set(f"dataset_validation:{dataset_id}:cancelled", "1", ex=3600)

    # Reset validation status
    db.datasets.update_one(
        {"_id": ObjectId(dataset_id)},
        {
            "$set": {
                "validation_status": "pending",
                "validation_progress": 0,
                "validation_task_id": None,
                "validation_error": None,
                "setup_step": 2,
            }
        },
    )

    # Delete all build records for this dataset
    result = db.dataset_builds.delete_many({"dataset_id": ObjectId(dataset_id)})

    return {
        "message": f"Reset validation. Deleted {result.deleted_count} build records."
    }


@router.post("/{dataset_id}/reset-step2")
async def reset_step2(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Reset Step 2 data - delete repos and build records when going back to Step 1."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Cancel any running validation task
    redis = await get_redis()
    await redis.set(f"dataset_validation:{dataset_id}:cancelled", "1", ex=3600)

    # Delete all enrichment repositories for this dataset
    repos_result = db.enrichment_repositories.delete_many(
        {"dataset_id": ObjectId(dataset_id)}
    )

    # Delete all build records for this dataset
    builds_result = db.dataset_builds.delete_many({"dataset_id": ObjectId(dataset_id)})

    # Reset dataset state
    db.datasets.update_one(
        {"_id": ObjectId(dataset_id)},
        {
            "$set": {
                "validation_status": "pending",
                "validation_progress": 0,
                "validation_task_id": None,
                "validation_error": None,
                "validation_stats": {
                    "repos_total": 0,
                    "repos_valid": 0,
                    "repos_invalid": 0,
                    "repos_not_found": 0,
                    "builds_total": 0,
                    "builds_found": 0,
                    "builds_not_found": 0,
                },
                "source_languages": [],
                "test_frameworks": [],
                "setup_step": 1,
            }
        },
    )

    return {
        "message": f"Reset Step 2. Deleted {repos_result.deleted_count} repos and {builds_result.deleted_count} builds."
    }


@router.put("/{dataset_id}/repos", response_model=SaveReposResponse)
async def update_repos(
    dataset_id: str,
    request: SaveReposRequest,
    db: Database = Depends(get_db),
):
    """Update existing repo configurations. Used when editing Step 2 settings."""
    dataset = db.datasets.find_one({"_id": ObjectId(dataset_id)})
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    updated_count = 0
    for repo_config in request.repos:
        result = db.enrichment_repositories.update_one(
            {
                "dataset_id": ObjectId(dataset_id),
                "full_name": repo_config.full_name,
            },
            {
                "$set": {
                    "ci_provider": repo_config.ci_provider,
                    "source_languages": repo_config.source_languages,
                    "test_frameworks": repo_config.test_frameworks,
                }
            },
        )
        if result.modified_count > 0:
            updated_count += 1

    return SaveReposResponse(
        saved=updated_count, message=f"Updated {updated_count} repositories"
    )
