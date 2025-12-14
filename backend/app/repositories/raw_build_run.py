"""Repository for RawBuildRun entities (shared raw build run data)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.entities.raw_build_run import RawBuildRun
from app.repositories.base import BaseRepository


class RawBuildRunRepository(BaseRepository[RawBuildRun]):
    """Repository for RawBuildRun entities - shared across all flows."""

    def __init__(self, db) -> None:
        super().__init__(db, "raw_build_runs", RawBuildRun)

    def find_by_build_id(
        self,
        raw_repo_id: ObjectId,
        build_id: str,
    ) -> Optional[RawBuildRun]:
        """Find a build run by repo and build_id."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "build_id": build_id,
            }
        )
        return RawBuildRun(**doc) if doc else None

    def find_by_repo_and_build_id(
        self,
        repo_id: str,
        build_id: str,
    ) -> Optional[RawBuildRun]:
        """Convenience method - accepts string repo_id for compatibility."""
        return self.find_by_build_id(ObjectId(repo_id), build_id)

    def find_by_commit_sha(
        self,
        raw_repo_id: ObjectId,
        commit_sha: str,
    ) -> Optional[RawBuildRun]:
        """Find a build run by repo and commit SHA."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "commit_sha": commit_sha,
            }
        )
        return RawBuildRun(**doc) if doc else None

    def list_by_repo(
        self,
        raw_repo_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> tuple[List[RawBuildRun], int]:
        """List build runs for a repository with pagination."""
        query: Dict[str, Any] = {"raw_repo_id": raw_repo_id}
        if since:
            query["created_at"] = {"$gte": since}

        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )
        items = [RawBuildRun(**doc) for doc in cursor]
        return items, total

    def upsert_build_run(
        self,
        raw_repo_id: ObjectId,
        build_id: str,
        **kwargs,
    ) -> RawBuildRun:
        """Upsert a build run by repo and build_id."""
        existing = self.find_by_build_id(raw_repo_id, build_id)
        if existing and existing.id:
            # Update existing
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            if update_data:
                self.collection.update_one({"_id": existing.id}, {"$set": update_data})
            result = self.find_by_id(existing.id)
            return result if result else existing
        else:
            # Create new
            run = RawBuildRun(raw_repo_id=raw_repo_id, build_id=build_id, **kwargs)
            return self.insert_one(run)

    def get_latest_run(
        self,
        raw_repo_id: ObjectId,
    ) -> Optional[RawBuildRun]:
        """Get the most recent build run for a repository."""
        doc = (
            self.collection.find({"raw_repo_id": raw_repo_id})
            .sort("created_at", -1)
            .limit(1)
        )
        docs = list(doc)
        return RawBuildRun(**docs[0]) if docs else None

    def count_by_repo(self, raw_repo_id: ObjectId) -> int:
        """Count build runs for a repository."""
        return self.collection.count_documents({"raw_repo_id": raw_repo_id})

    def update_effective_sha(self, build_run_id: ObjectId, effective_sha: str) -> bool:
        """Update effective_sha for a build run (used for replayed fork commits)."""
        result = self.collection.update_one(
            {"_id": build_run_id},
            {"$set": {"effective_sha": effective_sha}},
        )
        return result.modified_count > 0
