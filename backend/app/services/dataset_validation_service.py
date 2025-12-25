"""Service for dataset validation operations."""

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.core.redis import get_async_redis
from app.entities.dataset import DatasetProject, DatasetValidationStatus
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
from app.repositories.dataset_repository import DatasetRepository
from app.tasks.dataset_validation import dataset_validation_orchestrator


class DatasetValidationService:
    """Service handling dataset validation operations."""

    def __init__(self, db: Database):
        self.db = db
        self.dataset_repo = DatasetRepository(db)
        self.dataset_repo_stats_repo = DatasetRepoStatsRepository(db)
        self.build_repo = DatasetBuildRepository(db)

    def _get_dataset_or_404(self, dataset_id: str) -> DatasetProject:
        """Get dataset or raise 404."""

        dataset = self.dataset_repo.find_one({"_id": ObjectId(dataset_id)})
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return dataset

    async def start_validation(self, dataset_id: str) -> dict:
        """Start async validation of builds in a dataset."""
        dataset = self._get_dataset_or_404(dataset_id)

        if dataset.validation_status == DatasetValidationStatus.VALIDATING:
            raise HTTPException(status_code=400, detail="Validation is already in progress")

        mapped_fields = dataset.mapped_fields or {}
        if not mapped_fields.build_id or not mapped_fields.repo_name:
            raise HTTPException(
                status_code=400,
                detail="Dataset mapping not configured. Please map build_id and repo_name columns.",
            )

        # Clear any existing cancel flag before starting/resuming
        redis = await get_async_redis()
        await redis.delete(f"dataset_validation:{dataset_id}:cancelled")

        task = dataset_validation_orchestrator.delay(dataset_id)
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

    def get_validation_summary(self, dataset_id: str) -> dict:
        """Get detailed validation summary including repo breakdown.

        Returns dataset validation status with per-repository results
        from validation_stats.repo_stats.
        """
        from app.repositories.raw_repository import RawRepositoryRepository

        dataset = self._get_dataset_or_404(dataset_id)

        # Fetch repo stats from separate collection
        repo_stats = self.dataset_repo_stats_repo.find_by_dataset(dataset_id)

        # Get raw_repo_ids for batch lookup
        raw_repo_ids = [str(stat.raw_repo_id) for stat in repo_stats]
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repos = raw_repo_repo.find_by_ids(raw_repo_ids)
        raw_repo_map = {str(r.id): r for r in raw_repos}

        repos_list = []
        for stat in repo_stats:
            raw_repo = raw_repo_map.get(str(stat.raw_repo_id))
            repos_list.append(
                {
                    "id": str(stat.raw_repo_id),
                    "raw_repo_id": str(stat.raw_repo_id),
                    "github_repo_id": raw_repo.github_repo_id if raw_repo else None,
                    "full_name": stat.full_name,
                    "ci_provider": stat.ci_provider.value
                    if hasattr(stat.ci_provider, "value")
                    else str(stat.ci_provider),
                    "validation_status": "valid" if stat.is_valid else "invalid",
                    "validation_error": stat.validation_error,
                    "builds_total": stat.builds_total,
                    "builds_found": stat.builds_found,
                    "builds_not_found": stat.builds_not_found,
                    "builds_filtered": stat.builds_filtered,
                }
            )

        return {
            "dataset_id": dataset_id,
            "status": dataset.validation_status or DatasetValidationStatus.PENDING,
            "stats": dataset.validation_stats or {},
            "repos": repos_list,
        }

    def get_dataset_repos(
        self,
        dataset_id: str,
        skip: int = 0,
        limit: int = 20,
        search: str = None,
    ) -> dict:
        """Get paginated list of repositories for a dataset."""
        self._get_dataset_or_404(dataset_id)

        # Build query
        filter_query = {"dataset_id": ObjectId(dataset_id)}
        if search:
            filter_query["full_name"] = {"$regex": search, "$options": "i"}

        # Get total count
        total = self.dataset_repo_stats_repo.collection.count_documents(filter_query)

        # Get page
        stats = (
            self.dataset_repo_stats_repo.collection.find(filter_query)
            .sort("full_name", 1)
            .skip(skip)
            .limit(limit)
        )

        items = []
        for stat in stats:
            items.append(
                {
                    "id": str(stat["_id"]),
                    "raw_repo_id": str(stat["raw_repo_id"]) if stat.get("raw_repo_id") else None,
                    "full_name": stat["full_name"],
                    "is_valid": stat.get("is_valid", False),
                    "validation_status": "valid" if stat.get("is_valid") else "invalid",
                    "validation_error": stat.get("validation_error"),
                    "builds_total": stat.get("builds_total", 0),
                    "builds_found": stat.get("builds_found", 0),
                    "builds_not_found": stat.get("builds_not_found", 0),
                    "builds_filtered": stat.get("builds_filtered", 0),
                }
            )

        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    async def cancel_validation(self, dataset_id: str) -> dict:
        """Cancel ongoing validation (resumable)."""
        dataset = self._get_dataset_or_404(dataset_id)

        if dataset.validation_status != DatasetValidationStatus.VALIDATING:
            raise HTTPException(status_code=400, detail="No validation in progress")

        redis = await get_async_redis()
        await redis.set(
            f"dataset_validation:{dataset_id}:cancelled",
            "1",
            ex=3600,
        )

        # Update status to CANCELLED (allows resume)
        self.dataset_repo.update_one(
            dataset_id,
            {"validation_status": DatasetValidationStatus.CANCELLED},
        )

        return {"message": "Validation paused. You can resume later.", "can_resume": True}

    async def reset_validation(self, dataset_id: str) -> dict:
        """Reset validation state and delete build records."""
        self._get_dataset_or_404(dataset_id)

        # Cancel any running task
        redis = await get_async_redis()
        await redis.set(f"dataset_validation:{dataset_id}:cancelled", "1", ex=3600)

        # Reset validation status
        self.dataset_repo.update_one(
            dataset_id,
            {
                "validation_status": "pending",
                "validation_progress": 0,
                "validation_task_id": None,
                "validation_error": None,
                "setup_step": 2,
            },
        )

        # Delete all build records for this dataset
        self.build_repo.delete_by_dataset(dataset_id)

        # Delete repo stats
        deleted_stats = self.dataset_repo_stats_repo.delete_by_dataset(dataset_id)
        # builds are deleted by delete_by_dataset above

        return {"message": f"Reset validation. Stats deleted: {deleted_stats}"}
