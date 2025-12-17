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

    def find_active_by_raw_repo_id(
        self,
        raw_repo_id: ObjectId,
    ) -> Optional[ModelRepoConfig]:
        """
        Find the active (non-deleted) config for a raw repository.

        Used by webhook to find the 1:1 mapped config for processing.
        Returns None if no active config exists.
        """
        doc = self.collection.find_one(
            {
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
        query: Optional[dict] = None,
        include_deleted: bool = False,
    ) -> tuple[List[ModelRepoConfig], int]:
        """List all configs for a user with pagination."""
        if query is None:
            query = {}
        query["user_id"] = user_id
        if not include_deleted:
            query["is_deleted"] = {"$ne": True}

        return self.paginate(query, sort=[("created_at", -1)], skip=skip, limit=limit)

    def list_with_access_control(
        self,
        user_id: ObjectId,
        user_role: str,
        skip: int = 0,
        limit: int = 100,
        search_query: Optional[str] = None,
        include_deleted: bool = False,
        github_accessible_repos: Optional[List[str]] = None,
    ) -> tuple[List[ModelRepoConfig], int]:
        """
        List repos with RBAC access control.

        - Admin: Can see all repos
        - User: Can see public repos + repos where they are in granted_user_ids
                + repos they have access to on GitHub (if github_accessible_repos provided)

        Args:
            github_accessible_repos: List of repo full_names user can access on GitHub
                                    (synced during login, used for auto-access)
        """
        base_query: dict = {}

        if not include_deleted:
            base_query["is_deleted"] = {"$ne": True}

        if search_query:
            base_query["full_name"] = {"$regex": search_query, "$options": "i"}

        if user_role == "admin":
            # Admin sees everything
            pass
        else:
            # Regular user sees:
            # 1. Public repos (visibility = "public" or visibility not set)
            # 2. Private repos where they are granted access
            # 3. Repos they have access to on GitHub (via github_accessible_repos)
            access_conditions = [
                {"visibility": {"$in": ["public", None]}},
                {"visibility": {"$exists": False}},  # Backward compatibility
                {"granted_user_ids": user_id},
            ]

            # Add GitHub accessible repos condition if provided
            # NOTE: Currently disabled - uncomment when ready to enforce RBAC
            # if github_accessible_repos:
            #     access_conditions.append({"full_name": {"$in": github_accessible_repos}})

            base_query["$or"] = access_conditions

        return self.paginate(
            base_query, sort=[("created_at", -1)], skip=skip, limit=limit
        )

    def can_user_access(
        self,
        repo_id: ObjectId,
        user_id: ObjectId,
        user_role: str,
        github_accessible_repos: Optional[List[str]] = None,
    ) -> bool:
        """
        Check if a user can access a specific repository.

        - Admin: Can access any repo
        - User: Can access public repos or repos where granted
                or repos they have access to on GitHub

        Args:
            github_accessible_repos: List of repo full_names user can access on GitHub
        """
        if user_role == "admin":
            return True

        repo = self.find_by_id(repo_id)
        if not repo:
            return False

        visibility = getattr(repo, "visibility", "public")
        if visibility == "public":
            return True

        granted_ids = getattr(repo, "granted_user_ids", [])
        if user_id in granted_ids:
            return True

        # Check GitHub accessible repos
        # NOTE: Currently disabled - uncomment when ready to enforce RBAC
        # if github_accessible_repos and repo.full_name in github_accessible_repos:
        #     return True

        return False

    def update_repository(
        self,
        repo_id: str,
        updates: dict,
    ) -> None:
        """Update a repository config by ID."""
        updates["updated_at"] = datetime.utcnow()
        self.collection.update_one({"_id": ObjectId(repo_id)}, {"$set": updates})

    def find_by_id(self, config_id: str) -> Optional[ModelRepoConfig]:
        """Find config by ID."""
        doc = self.collection.find_one({"_id": ObjectId(config_id)})
        return ModelRepoConfig(**doc) if doc else None

    def find_one(self, query: dict) -> Optional[ModelRepoConfig]:
        """Find one config by query."""
        doc = self.collection.find_one(query)
        return ModelRepoConfig(**doc) if doc else None

    def find_by_full_name(self, full_name: str) -> Optional[ModelRepoConfig]:
        """Find config by full_name (e.g., 'owner/repo')."""
        doc = self.collection.find_one(
            {"full_name": full_name, "is_deleted": {"$ne": True}}
        )
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
