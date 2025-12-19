"""Service for dataset validation operations."""

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.tasks.dataset_validation import start_validation
from app.core.redis import get_async_redis
from app.entities.dataset import DatasetProject, DatasetValidationStatus


class DatasetValidationService:
    """Service handling dataset validation operations."""

    def __init__(self, db: Database):
        self.db = db
        self.dataset_repo = DatasetRepository(db)
        self.enrichment_repo = DatasetRepoConfigRepository(db)
        self.build_repo = DatasetBuildRepository(db)

    def _get_dataset_or_404(self, dataset_id: str) -> DatasetProject:
        """Get dataset or raise 404."""

        dataset = self.dataset_repo.find_one({"_id": ObjectId(dataset_id)})
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return dataset

    def save_repos(self, dataset_id: str, repos) -> dict:
        """
        Update repository configs from Step 2.

        Since validate_repos_task already created DatasetRepoConfig and RawRepository
        during upload, this method only updates user-configurable fields:
        - ci_provider
        - source_languages
        - test_frameworks

        Args:
            dataset_id: Dataset ID
            repos: List of RepoConfigRequest DTOs with id, ci_provider, source_languages, test_frameworks
        """
        self._get_dataset_or_404(dataset_id)

        updated_count = 0

        for repo_config in repos:
            # Update config by id directly
            self.enrichment_repo.update_config(
                config_id=repo_config.id,
                updates={
                    "ci_provider": repo_config.ci_provider,
                    "source_languages": repo_config.source_languages,
                    "test_frameworks": repo_config.test_frameworks,
                },
            )
            updated_count += 1

        return {
            "saved": updated_count,
            "message": f"Updated {updated_count} repository configs.",
        }

    async def start_validation(self, dataset_id: str) -> dict:
        """Start async validation of builds in a dataset."""
        dataset = self._get_dataset_or_404(dataset_id)

        if dataset.validation_status == DatasetValidationStatus.VALIDATING:
            raise HTTPException(
                status_code=400, detail="Validation is already in progress"
            )

        mapped_fields = dataset.mapped_fields or {}
        if not mapped_fields.build_id or not mapped_fields.repo_name:
            raise HTTPException(
                status_code=400,
                detail="Dataset mapping not configured. Please map build_id and repo_name columns.",
            )

        # Check at least one repo exists
        repo_count = self.enrichment_repo.count_by_dataset(ObjectId(dataset_id))
        if repo_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No validated repositories found. Please complete Step 2 first.",
            )

        # Clear any existing cancel flag before starting/resuming
        redis = await get_async_redis()
        await redis.delete(f"dataset_validation:{dataset_id}:cancelled")

        task = start_validation.delay(dataset_id)
        return {"task_id": task.id, "message": "Validation started"}

    def get_validation_status(self, dataset_id: str) -> dict:
        """Get current validation progress and status."""
        dataset = self._get_dataset_or_404(dataset_id)

        return {
            "dataset_id": dataset_id,
            "status": dataset.validation_status or DatasetValidationStatus.PENDING,
            "progress": dataset.validation_progress or 0,
            "task_id": dataset.validation_task_id,
            "started_at": dataset.validation_started_at,
            "completed_at": dataset.validation_completed_at,
            "error": dataset.validation_error,
            "stats": dataset.validation_stats,
        }

    async def cancel_validation(self, dataset_id: str) -> dict:
        """Cancel ongoing validation."""
        dataset = self._get_dataset_or_404(dataset_id)

        if dataset.validation_status != DatasetValidationStatus.VALIDATING:
            raise HTTPException(status_code=400, detail="No validation in progress")

        redis = await get_async_redis()
        await redis.set(
            f"dataset_validation:{dataset_id}:cancelled",
            "1",
            ex=3600,
        )

        return {"message": "Cancellation requested"}

    def get_validation_summary(self, dataset_id: str) -> dict:
        """Get detailed validation summary including repo breakdown."""
        dataset = self._get_dataset_or_404(dataset_id)

        validation_status = dataset.validation_status or DatasetValidationStatus.PENDING
        if validation_status not in (
            DatasetValidationStatus.COMPLETED,
            DatasetValidationStatus.FAILED,
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Validation not completed. Current status: {validation_status}",
            )

        stats_dict = dataset.validation_stats or {}

        repos = self.enrichment_repo.find_by_dataset(dataset_id)
        repo_results = []
        for repo in repos:
            repo_results.append(
                {
                    "id": str(repo.id),
                    "full_name": repo.full_name,
                    "validation_status": (
                        repo.validation_status.value
                        if hasattr(repo.validation_status, "value")
                        else repo.validation_status
                    ),
                    "validation_error": repo.validation_error,
                    "builds_found": repo.builds_found,
                    "builds_not_found": repo.builds_not_found,
                }
            )

        return {
            "dataset_id": dataset_id,
            "status": validation_status,
            "stats": stats_dict,
            "repos": repo_results,
        }

    async def reset_validation(self, dataset_id: str) -> dict:
        """Reset validation state and delete build records."""
        self._get_dataset_or_404(dataset_id)

        # Cancel any running task
        redis = await get_async_redis()
        await redis.set(f"dataset_validation:{dataset_id}:cancelled", "1", ex=3600)

        # Reset validation status
        self.db.datasets.update_one(
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
        deleted_count = self.build_repo.delete_by_dataset(dataset_id)

        return {"message": f"Reset validation. Deleted {deleted_count} build records."}

    async def reset_step2(self, dataset_id: str) -> dict:
        """Reset Step 2 data - delete repos and build records."""
        self._get_dataset_or_404(dataset_id)

        # Cancel any running validation task
        redis = await get_async_redis()
        await redis.set(f"dataset_validation:{dataset_id}:cancelled", "1", ex=3600)

        # Delete all enrichment repositories for this dataset
        repos_deleted = self.enrichment_repo.delete_by_dataset(dataset_id)

        # Delete all build records for this dataset
        builds_deleted = self.build_repo.delete_by_dataset(dataset_id)

        # Reset dataset state
        self.db.datasets.update_one(
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
                    "mapped_fields": {
                        "build_id": None,
                        "repo_name": None,
                    },
                    "source_languages": [],
                    "test_frameworks": [],
                    "setup_step": 1,
                }
            },
        )

        return {
            "message": f"Reset Step 2. Deleted {repos_deleted} repos and {builds_deleted} builds."
        }
