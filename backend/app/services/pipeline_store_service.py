"""Pipeline store service using repository pattern - compatibility layer"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.available_repository import AvailableRepositoryRepository


class PipelineStore:
    """
    Facade for persisting pipeline entities.
    This is a compatibility layer that uses repositories internally.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.repo_repo = ImportedRepositoryRepository(db)
        self.available_repo_repo = AvailableRepositoryRepository(db)

    def upsert_repository(
        self,
        *,
        user_id: Optional[str],
        provider: str,
        full_name: str,
        default_branch: str,
        is_private: bool,
        main_lang: Optional[str],
        github_repo_id: Optional[int],
        metadata: Dict[str, Any],
        last_scanned_at: Optional[datetime] = None,
        installation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upsert a repository"""
        return self.repo_repo.upsert_repository(
            user_id=user_id,
            provider=provider,
            full_name=full_name,
            default_branch=default_branch,
            is_private=is_private,
            main_lang=main_lang,
            github_repo_id=github_repo_id,
            metadata=metadata,
            last_scanned_at=last_scanned_at,
            installation_id=installation_id,
        )

    def update_repository(
        self, repo_id: str | ObjectId, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a repository"""
        return self.repo_repo.update_repository(str(repo_id), updates)

    def list_repositories(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List repositories"""
        return self.repo_repo.list_by_user(user_id)

    def get_repository(self, repo_id: str | ObjectId) -> Optional[Dict[str, Any]]:
        """Get a repository by ID"""
        return self.repo_repo.find_by_id(str(repo_id))

    def upsert_available_repository(
        self,
        user_id: str | ObjectId,
        repo_data: Dict[str, Any],
        installation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upsert an available repository"""
        return self.available_repo_repo.upsert_available_repo(
            user_id=user_id, repo_data=repo_data, installation_id=installation_id
        )

    def discover_available_repositories(
        self, user_id: str | ObjectId, q: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Discover available repositories that are not yet imported.
        Supports filtering by name (q) and pagination (limit).
        """
        filters = {"imported": {"$ne": True}}

        if q:
            filters["full_name"] = {"$regex": q, "$options": "i"}

        repos = self.available_repo_repo.list_by_user(user_id, filters)
        repos = repos[:limit]
        items = []
        for repo in repos:
            full_name = repo.get("full_name")
            if not full_name:
                continue

            items.append(
                {
                    "full_name": full_name,
                    "description": repo.get("description"),
                    "default_branch": repo.get("default_branch"),
                    "private": bool(repo.get("private")),
                    "owner": full_name.split("/")[0],
                    "installed": False,
                    "requires_installation": False,
                    "installation_id": repo.get("installation_id"),
                    "html_url": repo.get("html_url"),
                }
            )

        return items

    def clear_available_repositories(self, user_id: str):
        """Clear cached available repositories for a user"""
        self.available_repo_repo.delete_by_user(user_id)

    def delete_stale_available_repositories(
        self, user_id: str, active_full_names: List[str]
    ):
        """Remove available repositories that are no longer active"""
        self.available_repo_repo.delete_stale_repos(user_id, active_full_names)
