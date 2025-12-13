"""Service for dataset validation operations."""

from typing import List, Optional
from datetime import datetime

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.entities import ValidationStats, RepoValidationStatus
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.enrichment_repo_repository import EnrichmentRepoRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.tasks.dataset_validation import validate_dataset_task
from app.core.redis import get_async_redis


class RepoConfig:
    """Config for a repository from request."""

    def __init__(
        self,
        full_name: str,
        ci_provider: str = "github_actions",
        source_languages: List[str] = None,
        test_frameworks: List[str] = None,
        validation_status: str = "valid",
    ):
        self.full_name = full_name
        self.ci_provider = ci_provider
        self.source_languages = source_languages or []
        self.test_frameworks = test_frameworks or []
        self.validation_status = validation_status


class DatasetValidationService:
    """Service handling dataset validation operations."""

    def __init__(self, db: Database):
        self.db = db
        self.dataset_repo = DatasetRepository(db)
        self.enrichment_repo = EnrichmentRepoRepository(db)
        self.build_repo = DatasetBuildRepository(db)

    def _get_dataset_or_404(self, dataset_id: str) -> dict:
        """Get dataset or raise 404."""
        dataset = self.db.datasets.find_one({"_id": ObjectId(dataset_id)})
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return dataset

    def save_repos(self, dataset_id: str, repos: List[RepoConfig]) -> dict:
        """Save repository configs from Step 2."""
        self._get_dataset_or_404(dataset_id)

        saved_count = 0
        for repo_config in repos:
            # Skip invalid repos
            if repo_config.validation_status not in ("valid",):
                continue

            self.enrichment_repo.upsert_repo(
                dataset_id=dataset_id,
                full_name=repo_config.full_name,
                ci_provider=repo_config.ci_provider,
                source_languages=repo_config.source_languages,
                test_frameworks=repo_config.test_frameworks,
                validation_status=RepoValidationStatus.VALID,
            )
            saved_count += 1

        return {"saved": saved_count, "message": f"Saved {saved_count} repositories"}

    async def start_validation(self, dataset_id: str) -> dict:
        """Start async validation of builds in a dataset."""
        dataset = self._get_dataset_or_404(dataset_id)

        if dataset.get("validation_status") == "validating":
            raise HTTPException(
                status_code=400, detail="Validation is already in progress"
            )

        mapped_fields = dataset.get("mapped_fields", {})
        if not mapped_fields.get("build_id") or not mapped_fields.get("repo_name"):
            raise HTTPException(
                status_code=400,
                detail="Dataset mapping not configured. Please map build_id and repo_name columns.",
            )

        # Check at least one repo exists
        repo_count = self.enrichment_repo.count_by_dataset(dataset_id)
        if repo_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No validated repositories found. Please complete Step 2 first.",
            )

        # Clear any existing cancel flag before starting/resuming
        redis = await get_async_redis()
        await redis.delete(f"dataset_validation:{dataset_id}:cancelled")

        task = validate_dataset_task.delay(dataset_id)
        return {"task_id": task.id, "message": "Validation started"}

    def get_validation_status(self, dataset_id: str) -> dict:
        """Get current validation progress and status."""
        dataset = self._get_dataset_or_404(dataset_id)

        stats = None
        if dataset.get("validation_stats"):
            stats = ValidationStats(**dataset["validation_stats"])

        return {
            "dataset_id": dataset_id,
            "status": dataset.get("validation_status", "pending"),
            "progress": dataset.get("validation_progress", 0),
            "task_id": dataset.get("validation_task_id"),
            "started_at": dataset.get("validation_started_at"),
            "completed_at": dataset.get("validation_completed_at"),
            "error": dataset.get("validation_error"),
            "stats": stats,
        }

    async def cancel_validation(self, dataset_id: str) -> dict:
        """Cancel ongoing validation."""
        dataset = self._get_dataset_or_404(dataset_id)

        if dataset.get("validation_status") != "validating":
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

        validation_status = dataset.get("validation_status", "pending")
        if validation_status not in ("completed", "failed"):
            raise HTTPException(
                status_code=400,
                detail=f"Validation not completed. Current status: {validation_status}",
            )

        stats_dict = dataset.get("validation_stats", {})
        stats = ValidationStats(**stats_dict)

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
                    "default_branch": repo.default_branch,
                    "is_private": repo.is_private,
                    "builds_found": repo.builds_found,
                    "builds_not_found": repo.builds_not_found,
                }
            )

        return {
            "dataset_id": dataset_id,
            "status": validation_status,
            "stats": stats,
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

    def update_repos(self, dataset_id: str, repos: List[RepoConfig]) -> dict:
        """Update existing repo configurations."""
        self._get_dataset_or_404(dataset_id)

        updated_count = 0
        for repo_config in repos:
            updated = self.enrichment_repo.update_repo_config(
                dataset_id=dataset_id,
                full_name=repo_config.full_name,
                ci_provider=repo_config.ci_provider,
                source_languages=repo_config.source_languages,
                test_frameworks=repo_config.test_frameworks,
            )
            if updated:
                updated_count += 1

        return {
            "saved": updated_count,
            "message": f"Updated {updated_count} repositories",
        }
