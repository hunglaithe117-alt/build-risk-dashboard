"""Repository for RawRepository entities (shared raw GitHub repository data)."""

from typing import List, Optional

from bson import ObjectId

from app.entities.raw_repository import RawRepository
from app.repositories.base import BaseRepository


class RawRepositoryRepository(BaseRepository[RawRepository]):
    """Repository for RawRepository entities - shared across all flows."""

    def __init__(self, db) -> None:
        super().__init__(db, "raw_repositories", RawRepository)

    def find_by_full_name(self, full_name: str) -> Optional[RawRepository]:
        """Find repository by full name (owner/repo)."""
        doc = self.collection.find_one({"full_name": full_name})
        return RawRepository(**doc) if doc else None

    def find_by_github_repo_id(self, github_repo_id: int) -> Optional[RawRepository]:
        """Find repository by GitHub's internal repository ID."""
        doc = self.collection.find_one({"github_repo_id": github_repo_id})
        return RawRepository(**doc) if doc else None

    def upsert_by_full_name(
        self,
        full_name: str,
        **kwargs,
    ) -> RawRepository:
        """Upsert a repository by full_name, updating or creating as needed."""
        existing = self.find_by_full_name(full_name)
        if existing:
            # Update existing
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            if update_data:
                self.collection.update_one({"_id": existing.id}, {"$set": update_data})
            return self.find_by_id(existing.id)
        else:
            # Create new
            repo = RawRepository(full_name=full_name, **kwargs)
            return self.create(repo)

    def list_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[RawRepository], int]:
        """List all raw repositories with pagination."""
        total = self.collection.count_documents({})
        cursor = self.collection.find().skip(skip).limit(limit)
        items = [RawRepository(**doc) for doc in cursor]
        return items, total
