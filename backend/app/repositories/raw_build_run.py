from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument

from app.entities.base import validate_object_id
from app.entities.raw_build_run import RawBuildRun
from app.repositories.base import BaseRepository


class RawBuildRunRepository(BaseRepository[RawBuildRun]):
    """Repository for RawBuildRun entities - shared across all flows."""

    def __init__(self, db) -> None:
        super().__init__(db, "raw_build_runs", RawBuildRun)

    def find_by_business_key(
        self,
        raw_repo_id: str,
        build_id: str,
        provider: str,
    ) -> Optional[RawBuildRun]:
        oid = validate_object_id(raw_repo_id)
        if not oid:
            return None
        doc = self.collection.find_one(
            {
                "raw_repo_id": oid,
                "ci_run_id": build_id,
                "provider": provider,
            }
        )
        return RawBuildRun(**doc) if doc else None

    def find_by_build_id(
        self,
        raw_repo_id: ObjectId,
        build_id: str,
    ) -> Optional[RawBuildRun]:
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "ci_run_id": build_id,
            }
        )
        return RawBuildRun(**doc) if doc else None

    def find_by_repo_and_build_id(
        self,
        repo_id: str | ObjectId,
        build_id: str,
    ) -> Optional[RawBuildRun]:
        """Convenience method - accepts string repo_id for compatibility."""
        return self.find_by_build_id(self.ensure_object_id(repo_id), build_id)

    def find_by_commit_or_effective_sha(
        self,
        raw_repo_id: str,
        commit_sha: str,
    ) -> Optional[RawBuildRun]:
        """Find a build run by repo and commit SHA or effective SHA."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": validate_object_id(raw_repo_id),
                "$or": [
                    {"commit_sha": commit_sha},
                    {"effective_sha": commit_sha},
                ],
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

        return self.paginate(query, sort=[("created_at", -1)], skip=skip, limit=limit)

    def find_ids_by_build_ids(
        self,
        raw_repo_id: ObjectId,
        build_ids: List[str],
        provider: str,
    ) -> List[Dict[str, Any]]:
        """
        Batch query using $in to find multiple builds efficiently.
        Returns list of dicts with _id, commit_sha, effective_sha for each found build.
        """
        if not build_ids:
            return []

        cursor = self.collection.find(
            {
                "raw_repo_id": raw_repo_id,
                "ci_run_id": {"$in": build_ids},
                "provider": provider,
            },
            {
                "_id": 1,
                "commit_sha": 1,
                "effective_sha": 1,
            },  # Projection - only needed fields
        )
        return list(cursor)

    def upsert_by_business_key(
        self,
        raw_repo_id: ObjectId,
        build_id: str,
        provider: str,
        **kwargs,
    ) -> RawBuildRun:
        """
        Upsert by business key (raw_repo_id + build_id + provider).

        Uses atomic find_one_and_update for thread safety.
        This method ensures deduplication when the same build is
        fetched from both model flow and dataset flow.
        """
        update_data = {
            "raw_repo_id": raw_repo_id,
            "ci_run_id": build_id,
            "provider": provider,
            **{k: v for k, v in kwargs.items() if v is not None},
        }

        doc = self.collection.find_one_and_update(
            {"raw_repo_id": raw_repo_id, "ci_run_id": build_id, "provider": provider},
            {"$set": update_data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return RawBuildRun(**doc)

    def upsert_build_run(
        self,
        raw_repo_id: ObjectId,
        build_id: str,
        **kwargs,
    ) -> RawBuildRun:
        """
        Upsert a build run by repo and build_id.

        Note: This method doesn't include provider in the unique key.
        Consider using upsert_by_business_key for better deduplication.
        """
        # Extract provider from kwargs if available
        provider = kwargs.get("provider")
        if provider:
            return self.upsert_by_business_key(raw_repo_id, build_id, provider, **kwargs)

        # Legacy behavior: upsert by (raw_repo_id, build_id) only
        update_data = {
            "raw_repo_id": raw_repo_id,
            "ci_run_id": build_id,
            **{k: v for k, v in kwargs.items() if v is not None},
        }

        doc = self.collection.find_one_and_update(
            {"raw_repo_id": raw_repo_id, "ci_run_id": build_id},
            {"$set": update_data},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return RawBuildRun(**doc)

    def get_latest_run(
        self,
        raw_repo_id: ObjectId,
    ) -> Optional[RawBuildRun]:
        """Get the most recent build run for a repository."""
        doc = self.collection.find({"raw_repo_id": raw_repo_id}).sort("created_at", -1).limit(1)
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
