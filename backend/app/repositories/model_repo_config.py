"""Repository for ModelRepoConfig entities (user config for model training flow)."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.entities.model_repo_config import ModelRepoConfig
from app.entities.enums import ModelImportStatus, ModelSyncStatus
from app.repositories.base import BaseRepository


class ModelRepoConfigRepository(BaseRepository[ModelRepoConfig]):
    """Repository for ModelRepoConfig entities (Model training flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "model_repo_configs", ModelRepoConfig)

    def find_by_user_and_repo(
        self,
        user_id: ObjectId,
        raw_repo_id: ObjectId,
    ) -> Optional[ModelRepoConfig]:
        """Find config by user and raw repository."""
        doc = self.collection.find_one(
            {
                "user_id": user_id,
                "raw_repo_id": raw_repo_id,
                "is_deleted": {"$ne": True},
            }
        )
        return ModelRepoConfig(**doc) if doc else None

    def list_by_user(
        self,
        user_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> tuple[List[ModelRepoConfig], int]:
        """List all configs for a user with pagination."""
        query = {"user_id": user_id}
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}

        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )
        items = [ModelRepoConfig(**doc) for doc in cursor]
        return items, total

    def upsert_repository(
        self,
        user_id: str,
        full_name: str,
        data: dict,
    ) -> ModelRepoConfig:
        """Upsert a repository config by user and full_name."""
        existing = self.collection.find_one(
            {
                "user_id": ObjectId(user_id),
                "full_name": full_name,
                "is_deleted": {"$ne": True},
            }
        )

        if existing:
            # Update existing
            update_data = {**data, "updated_at": datetime.utcnow()}
            self.collection.update_one({"_id": existing["_id"]}, {"$set": update_data})
            return self.find_by_id(existing["_id"])
        else:
            # Create new
            config = ModelRepoConfig(
                user_id=ObjectId(user_id),
                full_name=full_name,
                **data,
            )
            return self.create(config)

    def update_repository(
        self,
        repo_id: str,
        updates: dict,
    ) -> None:
        """Update a repository config by ID."""
        updates["updated_at"] = datetime.utcnow()
        self.collection.update_one({"_id": ObjectId(repo_id)}, {"$set": updates})

    def find_by_id(self, config_id) -> Optional[ModelRepoConfig]:
        """Find config by ID."""
        doc = self.collection.find_one({"_id": ObjectId(config_id)})
        return ModelRepoConfig(**doc) if doc else None

    def find_one(self, query: dict) -> Optional[ModelRepoConfig]:
        """Find one config by query."""
        doc = self.collection.find_one(query)
        return ModelRepoConfig(**doc) if doc else None

    def update_import_status(
        self,
        config_id: ObjectId,
        status: ModelImportStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update import status for a config."""
        update = {
            "import_status": status.value if hasattr(status, "value") else status,
            "updated_at": datetime.utcnow(),
        }
        if status == ModelImportStatus.IMPORTING:
            update["import_started_at"] = datetime.utcnow()
        elif status in (ModelImportStatus.IMPORTED, ModelImportStatus.FAILED):
            update["import_completed_at"] = datetime.utcnow()
        if error:
            update["import_error"] = error

        self.collection.update_one({"_id": config_id}, {"$set": update})

    def update_sync_status(
        self,
        config_id: ObjectId,
        status: ModelSyncStatus,
        latest_run_created_at: Optional[datetime] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update sync status for a config."""
        update = {
            "last_sync_status": status.value if hasattr(status, "value") else status,
            "last_synced_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if latest_run_created_at:
            update["latest_synced_run_created_at"] = latest_run_created_at
        if error:
            update["last_sync_error"] = error

        self.collection.update_one({"_id": config_id}, {"$set": update})

    def increment_builds_imported(
        self,
        config_id: ObjectId,
        count: int = 1,
    ) -> None:
        """Increment the total builds imported count."""
        self.collection.update_one(
            {"_id": config_id},
            {
                "$inc": {"total_builds_imported": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

    def increment_builds_processed(
        self,
        config_id: ObjectId,
        count: int = 1,
    ) -> None:
        """Increment the total builds processed count."""
        self.collection.update_one(
            {"_id": config_id},
            {
                "$inc": {"total_builds_processed": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

    def soft_delete(self, config_id: ObjectId) -> None:
        """Soft delete a config."""
        self.collection.update_one(
            {"_id": config_id},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
