"""Repository repository for database operations"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo import ReturnDocument
from pymongo.database import Database

from app.models.entities.imported_repository import ImportedRepository
from .base import BaseRepository


class ImportedRepositoryRepository(BaseRepository[ImportedRepository]):
    """Repository for repository entities (yes, repo of repos!)"""

    def __init__(self, db: Database):
        super().__init__(db, "repositories", ImportedRepository)

    def find_by_full_name(
        self, provider: str, full_name: str
    ) -> Optional[ImportedRepository]:
        """Find a repository by provider and full name"""
        return self.find_one({"provider": provider, "full_name": full_name})

    def list_by_user(self, user_id: Optional[str] = None) -> List[ImportedRepository]:
        """List repositories for a user or all if no user specified"""
        query: Dict[str, Any] = {}
        if user_id is not None:
            query["user_id"] = self._to_object_id(user_id)
        return self.find_many(query, sort=[("created_at", -1)])

    def update_repository(
        self, repo_id: str, updates: Dict[str, Any]
    ) -> Optional[ImportedRepository]:
        payload = updates.copy()
        payload["updated_at"] = datetime.now(timezone.utc)
        return self.update_one(repo_id, payload)

    def upsert_repository(
        self, query: Dict[str, Any], data: Dict[str, Any]
    ) -> ImportedRepository:
        now = datetime.now(timezone.utc)

        update_op = {
            "$set": {**data, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        }

        if "created_at" in update_op["$set"]:
            del update_op["$set"]["created_at"]

        doc = self.collection.find_one_and_update(
            query, update_op, upsert=True, return_document=ReturnDocument.AFTER
        )

        return self._to_model(doc)
