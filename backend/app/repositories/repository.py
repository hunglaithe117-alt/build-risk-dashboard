"""Repository repository for database operations"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from .base import BaseRepository


class RepositoryRepository(BaseRepository):
    """Repository for repository entities (yes, repo of repos!)"""

    def __init__(self, db: Database):
        super().__init__(db, "repositories")

    def find_by_full_name(self, provider: str, full_name: str) -> Optional[Dict]:
        """Find a repository by provider and full name"""
        return self.find_one({"provider": provider, "full_name": full_name})

    def list_by_user(self, user_id: Optional[str] = None) -> List[Dict]:
        """List repositories for a user or all if no user specified"""
        query: Dict[str, Any] = {}
        if user_id is not None:
            query["user_id"] = self._to_object_id(user_id)
        return self.find_many(query, sort=[("created_at", -1)])

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
        """Insert or update a repository"""
        now = datetime.now(timezone.utc)
        existing = self.find_by_full_name(provider, full_name)

        owner_id = self._to_object_id(user_id) if user_id else None

        document = {
            "user_id": owner_id,
            "provider": provider,
            "full_name": full_name,
            "default_branch": default_branch,
            "is_private": is_private,
            "main_lang": main_lang,
            "github_repo_id": github_repo_id,
            "metadata": metadata,
            "updated_at": now,
        }

        # Preserve existing settings
        if existing:
            document["ci_provider"] = existing.get("ci_provider", "github_actions")
            document["monitoring_enabled"] = existing.get("monitoring_enabled", True)
            document["sync_status"] = existing.get("sync_status", "healthy")
            document["webhook_status"] = existing.get("webhook_status", "inactive")
            document["ci_token_status"] = existing.get("ci_token_status", "valid")
            document["tracked_branches"] = existing.get("tracked_branches") or [
                default_branch
            ]
            document["last_sync_error"] = existing.get("last_sync_error")
            document["notes"] = existing.get("notes")
        else:
            document["ci_provider"] = "github_actions"
            document["monitoring_enabled"] = True
            document["sync_status"] = "healthy"
            document["webhook_status"] = "inactive"
            document["ci_token_status"] = "valid"
            document["tracked_branches"] = [default_branch] if default_branch else []
            document["last_sync_error"] = None
            document["notes"] = None

        # Handle installation_id
        if installation_id is not None:
            document["installation_id"] = installation_id
        elif existing:
            document["installation_id"] = existing.get("installation_id")

        # Handle last_scanned_at
        if last_scanned_at is not None:
            document["last_scanned_at"] = last_scanned_at
        elif existing:
            document["last_scanned_at"] = existing.get("last_scanned_at")
        else:
            document["last_scanned_at"] = None

        if existing:
            self.collection.update_one({"_id": existing["_id"]}, {"$set": document})
            return self.find_by_id(existing["_id"])
        else:
            document["created_at"] = now
            return self.insert_one(document)

    def update_repository(
        self, repo_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update repository fields"""
        payload = updates.copy()
        if "tracked_branches" in payload and payload["tracked_branches"] is None:
            payload["tracked_branches"] = []
        payload["updated_at"] = datetime.now(timezone.utc)
        return self.update_one(repo_id, payload)
