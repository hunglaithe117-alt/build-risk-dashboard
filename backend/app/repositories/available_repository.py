"""Repository for available repository entities"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from .base import BaseRepository


class AvailableRepositoryRepository(BaseRepository):
    """Repository for available repository entities"""

    def __init__(self, db: Database):
        super().__init__(db, "available_repositories")
        # Create index on user_id and full_name for fast lookups
        self.collection.create_index([("user_id", 1), ("full_name", 1)], unique=True)

    def list_by_user(
        self, user_id: str | ObjectId, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict]:
        """List available repositories for a user with optional filters"""
        query = {"user_id": self._to_object_id(user_id)}
        if filters:
            query.update(filters)

        return self.find_many(query, sort=[("full_name", 1)])

    def upsert_available_repo(
        self,
        user_id: str | ObjectId,
        repo_data: Dict[str, Any],
        installation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upsert an available repository"""
        now = datetime.now(timezone.utc)
        user_oid = self._to_object_id(user_id)

        filter_query = {"user_id": user_oid, "full_name": repo_data["full_name"]}

        update_doc = {
            "user_id": user_oid,
            "full_name": repo_data["full_name"],
            "github_id": repo_data["id"],
            "private": repo_data["private"],
            "html_url": repo_data["html_url"],
            "description": repo_data.get("description"),
            "default_branch": repo_data.get("default_branch", "main"),
            "updated_at": now,
        }

        if installation_id:
            update_doc["installation_id"] = installation_id

        self.collection.update_one(filter_query, {"$set": update_doc}, upsert=True)

        return self.find_one(filter_query)

    def delete_by_user(self, user_id: str | ObjectId):
        """Delete all available repos for a user (e.g. before full sync)"""
        self.collection.delete_many({"user_id": self._to_object_id(user_id)})

    def delete_stale_repos(self, user_id: str | ObjectId, active_full_names: List[str]):
        """Delete repos that are not in the active list"""
        self.collection.delete_many(
            {
                "user_id": self._to_object_id(user_id),
                "full_name": {"$nin": active_full_names},
            }
        )
