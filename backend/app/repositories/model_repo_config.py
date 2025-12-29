"""Repository for ModelRepoConfig entities (user config for model training flow)."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from pymongo.client_session import ClientSession

from app.entities.model_repo_config import ModelImportStatus, ModelRepoConfig
from app.repositories.base import BaseRepository


class ModelRepoConfigRepository(BaseRepository[ModelRepoConfig]):
    """Repository for ModelRepoConfig entities (Model training flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "model_repo_configs", ModelRepoConfig)

    def find_by_user_and_repo(
        self,
        user_id: ObjectId | str,
        raw_repo_id: ObjectId | str,
    ) -> Optional[ModelRepoConfig]:
        """Find config by user and raw repository."""
        doc = self.collection.find_one(
            {
                "user_id": self.ensure_object_id(user_id),
                "raw_repo_id": self.ensure_object_id(raw_repo_id),
            }
        )
        return ModelRepoConfig(**doc) if doc else None

    def list_by_user(
        self,
        user_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
        query: Optional[dict] = None,
    ) -> tuple[List[ModelRepoConfig], int]:
        """List all configs for a user with pagination."""
        if query is None:
            query = {}
        query["user_id"] = user_id
        return self.paginate(query, sort=[("created_at", -1)], skip=skip, limit=limit)

    def list_with_access_control(
        self,
        user_id: ObjectId,
        user_role: str,
        skip: int = 0,
        limit: int = 100,
        search_query: Optional[str] = None,
        github_accessible_repos: Optional[List[str]] = None,
    ) -> tuple[List[ModelRepoConfig], int]:
        """List repos with RBAC access control based on GitHub membership."""
        base_query: dict = {}

        if search_query:
            base_query["full_name"] = {"$regex": search_query, "$options": "i"}

        if user_role == "admin":
            pass
        else:
            if github_accessible_repos:
                base_query["full_name"] = {"$in": github_accessible_repos}
            else:
                base_query["full_name"] = {"$in": []}

        return self.paginate(base_query, sort=[("created_at", -1)], skip=skip, limit=limit)

    def can_user_access(
        self,
        repo_id: ObjectId,
        user_id: ObjectId,
        user_role: str,
        github_accessible_repos: Optional[List[str]] = None,
    ) -> bool:
        """Check if a user can access a specific repository."""
        if user_role == "admin":
            return True

        repo = self.find_by_id(repo_id)
        if not repo:
            return False

        if github_accessible_repos and repo.full_name in github_accessible_repos:
            return True

        return False

    def update_repository(
        self,
        repo_id: str,
        updates: dict,
    ) -> None:
        """Update a repository config by ID."""
        updates["updated_at"] = datetime.utcnow()
        self.collection.update_one({"_id": ObjectId(repo_id)}, {"$set": updates})

    def find_by_id(self, config_id: str | ObjectId) -> Optional[ModelRepoConfig]:
        """Find config by ID."""
        doc = self.collection.find_one({"_id": self.ensure_object_id(config_id)})
        return ModelRepoConfig(**doc) if doc else None

    def find_one(self, query: dict) -> Optional[ModelRepoConfig]:
        """Find one config by query."""
        doc = self.collection.find_one(query)
        return ModelRepoConfig(**doc) if doc else None

    def find_by_full_name(self, full_name: str) -> Optional[ModelRepoConfig]:
        """Find config by full_name (e.g., 'owner/repo')."""
        doc = self.collection.find_one({"full_name": full_name})
        return ModelRepoConfig(**doc) if doc else None

    def update_status(
        self,
        config_id: ObjectId | str,
        status: ModelImportStatus,
        error: Optional[str] = None,
    ) -> None:
        """Update pipeline status for a config."""
        update = {
            "status": status.value if hasattr(status, "value") else status,
            "updated_at": datetime.utcnow(),
        }
        if status == ModelImportStatus.INGESTING:
            update["started_at"] = datetime.utcnow()
        elif status in (ModelImportStatus.IMPORTED, ModelImportStatus.FAILED):
            update["completed_at"] = datetime.utcnow()
            update["last_synced_at"] = datetime.utcnow()
        if error:
            update["error_message"] = error

        self.collection.update_one({"_id": self.ensure_object_id(config_id)}, {"$set": update})

    def increment_builds_fetched(
        self,
        config_id: ObjectId,
        count: int = 1,
    ) -> Optional[ModelRepoConfig]:
        """Increment the builds fetched count."""
        doc = self.collection.find_one_and_update(
            {"_id": config_id},
            {
                "$inc": {"builds_fetched": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )
        return ModelRepoConfig(**doc) if doc else None

    def increment_builds_completed(
        self,
        config_id: ObjectId,
        count: int = 1,
    ) -> Optional[ModelRepoConfig]:
        """Increment the builds completed count (after prediction)."""
        doc = self.collection.find_one_and_update(
            {"_id": config_id},
            {
                "$inc": {"builds_completed": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )
        return ModelRepoConfig(**doc) if doc else None

    def increment_builds_failed(
        self,
        config_id: ObjectId,
        count: int = 1,
    ) -> Optional[ModelRepoConfig]:
        """Increment the builds failed count."""
        doc = self.collection.find_one_and_update(
            {"_id": config_id},
            {
                "$inc": {"builds_failed": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )
        return ModelRepoConfig(**doc) if doc else None

    def hard_delete(self, config_id: ObjectId, session: "ClientSession | None" = None) -> int:
        """Hard delete a config (permanently removes from DB)."""
        result = self.collection.delete_one({"_id": config_id}, session=session)
        return result.deleted_count
