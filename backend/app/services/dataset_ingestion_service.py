"""Service for dataset ingestion operations (resource collection)."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.entities import DatasetIngestionStatus
from app.entities.dataset import DatasetProject
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository

logger = logging.getLogger(__name__)


class DatasetIngestionService:
    """Service handling dataset ingestion (resource collection) operations.

    Note: Ingestion is auto-triggered after validation completes.
    No manual start/cancel operations are exposed.
    """

    def __init__(self, db: Database):
        self.db = db
        self.dataset_repo = DatasetRepository(db)
        self.repo_config_repo = DatasetRepoConfigRepository(db)
        self.build_repo = DatasetBuildRepository(db)

    def _get_dataset_or_404(self, dataset_id: str) -> DatasetProject:
        dataset = self.dataset_repo.find_one({"_id": ObjectId(dataset_id)})
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return dataset

    def get_ingestion_status(self, dataset_id: str) -> Dict[str, Any]:
        """Get current ingestion progress and status."""
        dataset = self._get_dataset_or_404(dataset_id)

        return {
            "dataset_id": dataset_id,
            "status": dataset.ingestion_status or DatasetIngestionStatus.PENDING,
            "progress": dataset.ingestion_progress or 0,
            "task_id": dataset.ingestion_task_id,
            "started_at": dataset.ingestion_started_at,
            "completed_at": dataset.ingestion_completed_at,
            "error": dataset.ingestion_error,
            "stats": (
                dataset.ingestion_stats.model_dump()
                if dataset.ingestion_stats
                else None
            ),
        }

    def mark_completed(self, dataset_id: str, stats: Dict[str, Any]) -> None:
        """Mark ingestion as completed with stats."""
        self.dataset_repo.update_one(
            dataset_id,
            {
                "ingestion_status": DatasetIngestionStatus.COMPLETED,
                "ingestion_completed_at": datetime.now(timezone.utc),
                "ingestion_progress": 100,
                "ingestion_stats": stats,
                "setup_step": 4,
            },
        )

    def mark_failed(self, dataset_id: str, error: str) -> None:
        """Mark ingestion as failed with error."""
        self.dataset_repo.update_one(
            dataset_id,
            {
                "ingestion_status": DatasetIngestionStatus.FAILED,
                "ingestion_completed_at": datetime.now(timezone.utc),
                "ingestion_error": error,
            },
        )

    def update_progress(
        self, dataset_id: str, progress: int, stats: Dict[str, Any] = None
    ) -> None:
        """Update ingestion progress."""
        update = {"ingestion_progress": progress}
        if stats:
            update["ingestion_stats"] = stats
        self.dataset_repo.update_one(dataset_id, update)
