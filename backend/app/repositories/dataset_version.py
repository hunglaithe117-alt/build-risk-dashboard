"""DatasetVersion Repository - CRUD operations for dataset versions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from bson import ObjectId
from pymongo.client_session import ClientSession
from pymongo.database import Database

from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DatasetVersionRepository(BaseRepository[DatasetVersion]):
    """Repository for DatasetVersion entities."""

    COLLECTION_NAME = "dataset_versions"

    def __init__(self, db: Database):
        super().__init__(db, self.COLLECTION_NAME, DatasetVersion)

    def create(self, version: DatasetVersion) -> DatasetVersion:
        """Create a new dataset version."""
        data = version.model_dump(exclude={"id"})
        result = self.collection.insert_one(data)
        version.id = result.inserted_id
        return version

    def find_by_id(self, version_id: Union[str, ObjectId]) -> Optional[DatasetVersion]:
        """Find version by ID."""
        try:
            doc = self.collection.find_one({"_id": self.ensure_object_id(version_id)})
            if doc:
                return DatasetVersion(**doc)
            return None
        except (ValueError, TypeError):
            return None

    def find_by_dataset(
        self, dataset_id: Union[str, ObjectId], skip: int = 0, limit: int = 10
    ) -> tuple[List[DatasetVersion], int]:
        """Find all versions for a dataset, newest first, with pagination."""
        oid = self.ensure_object_id(dataset_id)
        query = {"dataset_id": oid}
        total = self.collection.count_documents(query)
        docs = self.collection.find(query).sort("version_number", -1).skip(skip).limit(limit)
        return [DatasetVersion(**doc) for doc in docs], total

    def find_active_by_dataset(self, dataset_id: Union[str, ObjectId]) -> Optional[DatasetVersion]:
        """Find running or pending version for a dataset."""
        oid = self.ensure_object_id(dataset_id)
        doc = self.collection.find_one(
            {
                "dataset_id": oid,
                "status": {"$in": [VersionStatus.PENDING, VersionStatus.PROCESSING]},
            }
        )
        if doc:
            return DatasetVersion(**doc)
        return None

    def find_latest_by_dataset(self, dataset_id: Union[str, ObjectId]) -> Optional[DatasetVersion]:
        """Find the latest completed version for a dataset."""
        oid = self.ensure_object_id(dataset_id)
        doc = self.collection.find_one(
            {"dataset_id": oid, "status": VersionStatus.COMPLETED},
            sort=[("version_number", -1)],
        )
        if doc:
            return DatasetVersion(**doc)
        return None

    def get_next_version_number(self, dataset_id: Union[str, ObjectId]) -> int:
        """Get the next version number for a dataset."""
        oid = self.ensure_object_id(dataset_id)
        latest = self.collection.find_one({"dataset_id": oid}, sort=[("version_number", -1)])
        if latest:
            return latest.get("version_number", 0) + 1
        return 1

    def find_by_user(
        self,
        user_id: Union[str, ObjectId],
        skip: int = 0,
        limit: int = 20,
    ) -> List[DatasetVersion]:
        """Find versions for a user."""
        oid = self.ensure_object_id(user_id)
        docs = self.collection.find({"user_id": oid}).sort("created_at", -1).skip(skip).limit(limit)
        return [DatasetVersion(**doc) for doc in docs]

    def update_one(self, version_id: Union[str, ObjectId], updates: Dict[str, Any]) -> bool:
        """Update a version by ID."""
        updates["updated_at"] = datetime.now(timezone.utc)
        result = self.collection.update_one(
            {"_id": self.ensure_object_id(version_id)}, {"$set": updates}
        )
        return result.modified_count > 0

    def update_progress(
        self,
        version_id: Union[str, ObjectId],
        processed_rows: int,
        enriched_rows: int,
        failed_rows: int,
    ) -> bool:
        """Update version progress atomically."""
        updates: Dict[str, Any] = {
            "processed_rows": processed_rows,
            "enriched_rows": enriched_rows,
            "failed_rows": failed_rows,
            "updated_at": datetime.now(timezone.utc),
        }

        update_ops: Dict[str, Any] = {"$set": updates}

        result = self.collection.update_one({"_id": self.ensure_object_id(version_id)}, update_ops)
        return result.modified_count > 0

    def increment_progress(
        self,
        version_id: Union[str, ObjectId],
        processed_rows: int = 0,
        enriched_rows: int = 0,
        failed_rows: int = 0,
    ) -> bool:
        """Increment version progress atomically using $inc.

        Used for batch processing where each task adds to the total.
        """
        inc_ops: Dict[str, int] = {}
        if processed_rows:
            inc_ops["processed_rows"] = processed_rows
        if enriched_rows:
            inc_ops["enriched_rows"] = enriched_rows
        if failed_rows:
            inc_ops["failed_rows"] = failed_rows

        if not inc_ops:
            return False

        result = self.collection.update_one(
            {"_id": self.ensure_object_id(version_id)},
            {
                "$inc": inc_ops,
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        return result.modified_count > 0

    def mark_started(self, version_id: Union[str, ObjectId], task_id: Optional[str] = None) -> bool:
        """Mark version as started processing."""
        updates: Dict[str, Any] = {
            "status": VersionStatus.PROCESSING,
            "started_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        if task_id:
            updates["task_id"] = task_id

        result = self.collection.update_one(
            {"_id": self.ensure_object_id(version_id)}, {"$set": updates}
        )
        return result.modified_count > 0

    def mark_completed(self, version_id: Union[str, ObjectId]) -> bool:
        """Mark version as completed."""
        result = self.collection.update_one(
            {"_id": self.ensure_object_id(version_id)},
            {
                "$set": {
                    "status": VersionStatus.COMPLETED,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    def mark_failed(self, version_id: Union[str, ObjectId], error: str) -> bool:
        """Mark version as failed."""
        result = self.collection.update_one(
            {"_id": self.ensure_object_id(version_id)},
            {
                "$set": {
                    "status": VersionStatus.FAILED,
                    "error_message": error,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    def mark_cancelled(self, version_id: Union[str, ObjectId]) -> bool:
        """Mark version as cancelled."""
        result = self.collection.update_one(
            {"_id": self.ensure_object_id(version_id)},
            {
                "$set": {
                    "status": VersionStatus.CANCELLED,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    def delete(
        self, version_id: Union[str, ObjectId], session: "ClientSession | None" = None
    ) -> bool:
        """Delete a version.

        Args:
            version_id: Version ID to delete
            session: Optional MongoDB session for transaction support
        """
        result = self.collection.delete_one(
            {"_id": self.ensure_object_id(version_id)}, session=session
        )
        return result.deleted_count > 0

    def delete_by_dataset(
        self, dataset_id: Union[str, ObjectId], session: "ClientSession | None" = None
    ) -> int:
        """Delete all versions for a dataset.

        Args:
            dataset_id: Dataset ID to delete versions for
            session: Optional MongoDB session for transaction support
        """
        oid = self.ensure_object_id(dataset_id)
        result = self.collection.delete_many({"dataset_id": oid}, session=session)
        return result.deleted_count

    def cleanup_old_versions(self, days: int = 30) -> int:
        """Delete completed versions older than N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.collection.delete_many(
            {
                "status": {
                    "$in": [
                        VersionStatus.COMPLETED,
                        VersionStatus.FAILED,
                        VersionStatus.CANCELLED,
                    ]
                },
                "completed_at": {"$lt": cutoff},
            }
        )
        return result.deleted_count

    def count_by_dataset(self, dataset_id: Union[str, ObjectId]) -> int:
        """Count versions for a dataset."""
        oid = self.ensure_object_id(dataset_id)
        return self.collection.count_documents({"dataset_id": oid})

    def count_completed_by_dataset(self, dataset_id: Union[str, ObjectId]) -> int:
        """Count completed versions for a dataset."""
        oid = self.ensure_object_id(dataset_id)
        return self.collection.count_documents(
            {"dataset_id": oid, "status": VersionStatus.COMPLETED}
        )
