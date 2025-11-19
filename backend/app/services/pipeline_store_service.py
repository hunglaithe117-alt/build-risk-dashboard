"""Pipeline store service using repository pattern - compatibility layer"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.repositories.repository import RepositoryRepository


class PipelineStore:
    """
    Facade for persisting pipeline entities.
    This is a compatibility layer that uses repositories internally.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.repo_repo = RepositoryRepository(db)

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
