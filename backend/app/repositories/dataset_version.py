"""
DatasetVersion Repository - CRUD operations for dataset versions.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.dataset_version import DatasetVersion, VersionStatus

logger = logging.getLogger(__name__)


class DatasetVersionRepository:
    """Repository for DatasetVersion entities."""

    COLLECTION_NAME = "dataset_versions"

    def __init__(self, db: Database):
        self.db = db
        self.collection = db[self.COLLECTION_NAME]

    def create(self, version: DatasetVersion) -> DatasetVersion:
        """Create a new dataset version."""
        data = version.model_dump(exclude={"id"})
        result = self.collection.insert_one(data)
        version.id = result.inserted_id
        return version

    def find_by_id(self, version_id: str) -> Optional[DatasetVersion]:
        """Find version by ID."""
        try:
            doc = self.collection.find_one({"_id": ObjectId(version_id)})
            if doc:
                return DatasetVersion(**doc)
            return None
        except Exception:
            return None

    def find_by_dataset(self, dataset_id: str, limit: int = 50) -> List[DatasetVersion]:
        """Find all versions for a dataset, newest first."""
        docs = (
            self.collection.find({"dataset_id": dataset_id})
            .sort("version_number", -1)
            .limit(limit)
        )
        return [DatasetVersion(**doc) for doc in docs]

    def find_active_by_dataset(self, dataset_id: str) -> Optional[DatasetVersion]:
        """Find running or pending version for a dataset."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "status": {"$in": [VersionStatus.PENDING, VersionStatus.PROCESSING]},
            }
        )
        if doc:
            return DatasetVersion(**doc)
        return None

    def find_latest_by_dataset(self, dataset_id: str) -> Optional[DatasetVersion]:
        """Find the latest completed version for a dataset."""
        doc = self.collection.find_one(
            {"dataset_id": dataset_id, "status": VersionStatus.COMPLETED},
            sort=[("version_number", -1)],
        )
        if doc:
            return DatasetVersion(**doc)
        return None

    def get_next_version_number(self, dataset_id: str) -> int:
        """Get the next version number for a dataset."""
        latest = self.collection.find_one(
            {"dataset_id": dataset_id}, sort=[("version_number", -1)]
        )
        if latest:
            return latest.get("version_number", 0) + 1
        return 1

    def find_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[DatasetVersion]:
        """Find versions for a user."""
        docs = (
            self.collection.find({"user_id": user_id})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [DatasetVersion(**doc) for doc in docs]

    def update_one(self, version_id: str, updates: Dict[str, Any]) -> bool:
        """Update a version by ID."""
        updates["updated_at"] = datetime.now(timezone.utc)
        result = self.collection.update_one(
            {"_id": ObjectId(version_id)}, {"$set": updates}
        )
        return result.modified_count > 0

    def update_progress(
        self,
        version_id: str,
        processed_rows: int,
        enriched_rows: int,
        failed_rows: int,
        row_error: Optional[Dict] = None,
    ) -> bool:
        """Update version progress atomically."""
        updates: Dict[str, Any] = {
            "processed_rows": processed_rows,
            "enriched_rows": enriched_rows,
            "failed_rows": failed_rows,
            "updated_at": datetime.now(timezone.utc),
        }

        update_ops: Dict[str, Any] = {"$set": updates}

        if row_error:
            update_ops["$push"] = {"row_errors": row_error}

        result = self.collection.update_one({"_id": ObjectId(version_id)}, update_ops)
        return result.modified_count > 0

    def mark_started(self, version_id: str, task_id: Optional[str] = None) -> bool:
        """Mark version as started processing."""
        updates: Dict[str, Any] = {
            "status": VersionStatus.PROCESSING,
            "started_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        if task_id:
            updates["task_id"] = task_id

        result = self.collection.update_one(
            {"_id": ObjectId(version_id)}, {"$set": updates}
        )
        return result.modified_count > 0

    def mark_completed(
        self,
        version_id: str,
        file_path: str,
        file_name: str,
        file_size_bytes: int,
    ) -> bool:
        """Mark version as completed."""
        result = self.collection.update_one(
            {"_id": ObjectId(version_id)},
            {
                "$set": {
                    "status": VersionStatus.COMPLETED,
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_size_bytes": file_size_bytes,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    def mark_failed(self, version_id: str, error: str) -> bool:
        """Mark version as failed."""
        result = self.collection.update_one(
            {"_id": ObjectId(version_id)},
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

    def mark_cancelled(self, version_id: str) -> bool:
        """Mark version as cancelled."""
        result = self.collection.update_one(
            {"_id": ObjectId(version_id)},
            {
                "$set": {
                    "status": VersionStatus.CANCELLED,
                    "completed_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    def add_auto_imported_repo(self, version_id: str, repo_name: str) -> bool:
        """Add a repo to the auto-imported list."""
        result = self.collection.update_one(
            {"_id": ObjectId(version_id)},
            {
                "$push": {"repos_auto_imported": repo_name},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )
        return result.modified_count > 0

    def delete(self, version_id: str) -> bool:
        """Delete a version."""
        result = self.collection.delete_one({"_id": ObjectId(version_id)})
        return result.deleted_count > 0

    def delete_by_dataset(self, dataset_id: str) -> int:
        """Delete all versions for a dataset."""
        result = self.collection.delete_many({"dataset_id": dataset_id})
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

    def count_by_dataset(self, dataset_id: str) -> int:
        """Count versions for a dataset."""
        return self.collection.count_documents({"dataset_id": dataset_id})

    def count_completed_by_dataset(self, dataset_id: str) -> int:
        """Count completed versions for a dataset."""
        return self.collection.count_documents(
            {"dataset_id": dataset_id, "status": VersionStatus.COMPLETED}
        )
