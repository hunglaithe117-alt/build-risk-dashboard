"""Repository for DatasetScan entity."""

from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.dataset_scan import DatasetScan, DatasetScanStatus
from .base import BaseRepository


class DatasetScanRepository(BaseRepository[DatasetScan]):
    """Repository for DatasetScan entities."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_scans", DatasetScan)

    def find_by_dataset(
        self, dataset_id: str, skip: int = 0, limit: int = 20
    ) -> tuple[List[DatasetScan], int]:
        """Find all scans for a dataset with pagination."""
        return self.paginate(
            {"dataset_id": self._to_object_id(dataset_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_active_by_dataset(self, dataset_id: str) -> List[DatasetScan]:
        """Find active (running/pending/partial) scans for a dataset."""
        return self.find_many(
            {
                "dataset_id": self._to_object_id(dataset_id),
                "status": {
                    "$in": [
                        DatasetScanStatus.PENDING.value,
                        DatasetScanStatus.RUNNING.value,
                        DatasetScanStatus.PARTIAL.value,
                    ]
                },
            }
        )

    def find_by_task_id(self, task_id: str) -> Optional[DatasetScan]:
        """Find a scan by its Celery task ID."""
        return self.find_one({"task_id": task_id})

    def update_progress(
        self,
        scan_id: str,
        scanned: int = 0,
        failed: int = 0,
        pending: int = 0,
    ) -> bool:
        """Update scan progress counters."""
        result = self.collection.update_one(
            {"_id": self._to_object_id(scan_id)},
            {
                "$set": {
                    "scanned_commits": scanned,
                    "failed_commits": failed,
                    "pending_commits": pending,
                }
            },
        )
        return result.modified_count > 0

    def mark_status(
        self,
        scan_id: str,
        status: DatasetScanStatus,
        error: Optional[str] = None,
        results_summary: Optional[dict] = None,
    ) -> bool:
        """Update scan status."""
        from datetime import datetime, timezone

        update: dict = {
            "status": status.value,
        }

        if status in (
            DatasetScanStatus.COMPLETED,
            DatasetScanStatus.FAILED,
            DatasetScanStatus.CANCELLED,
        ):
            update["completed_at"] = datetime.now(timezone.utc)

        if error:
            update["error_message"] = error

        if results_summary:
            update["results_summary"] = results_summary

        result = self.collection.update_one(
            {"_id": self._to_object_id(scan_id)},
            {"$set": update},
        )
        return result.modified_count > 0

    def count_by_dataset(self, dataset_id: str) -> int:
        """Count total scans for a dataset."""
        return self.collection.count_documents(
            {"dataset_id": self._to_object_id(dataset_id)}
        )
