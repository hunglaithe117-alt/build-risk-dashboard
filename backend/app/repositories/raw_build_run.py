"""Repository for RawWorkflowRun entities (shared raw workflow run data)."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from backend.app.entities.raw_build_run import RawWorkflowRun
from app.repositories.base import BaseRepository


class RawWorkflowRunRepository(BaseRepository[RawWorkflowRun]):
    """Repository for RawWorkflowRun entities - shared across all flows."""

    def __init__(self, db) -> None:
        super().__init__(db, "raw_workflow_runs", RawWorkflowRun)

    def find_by_workflow_run_id(
        self,
        raw_repo_id: ObjectId,
        workflow_run_id: int,
    ) -> Optional[RawWorkflowRun]:
        """Find a workflow run by repo and workflow_run_id."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "workflow_run_id": workflow_run_id,
            }
        )
        return RawWorkflowRun(**doc) if doc else None

    def find_by_repo_and_run_id(
        self,
        repo_id: str,
        workflow_run_id: int,
    ) -> Optional[RawWorkflowRun]:
        """Convenience method - accepts string repo_id for compatibility."""
        return self.find_by_workflow_run_id(ObjectId(repo_id), workflow_run_id)

    def find_by_head_sha(
        self,
        raw_repo_id: ObjectId,
        head_sha: str,
    ) -> Optional[RawWorkflowRun]:
        """Find a workflow run by repo and commit SHA."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "head_sha": head_sha,
            }
        )
        return RawWorkflowRun(**doc) if doc else None

    def list_by_repo(
        self,
        raw_repo_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> tuple[List[RawWorkflowRun], int]:
        """List workflow runs for a repository with pagination."""
        query = {"raw_repo_id": raw_repo_id}
        if since:
            query["build_created_at"] = {"$gte": since}

        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("build_created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        items = [RawWorkflowRun(**doc) for doc in cursor]
        return items, total

    def upsert_workflow_run(
        self,
        raw_repo_id: ObjectId,
        workflow_run_id: int,
        **kwargs,
    ) -> RawWorkflowRun:
        """Upsert a workflow run by repo and workflow_run_id."""
        existing = self.find_by_workflow_run_id(raw_repo_id, workflow_run_id)
        if existing:
            # Update existing
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            if update_data:
                self.collection.update_one({"_id": existing.id}, {"$set": update_data})
            return self.find_by_id(existing.id)
        else:
            # Create new
            run = RawWorkflowRun(
                raw_repo_id=raw_repo_id, workflow_run_id=workflow_run_id, **kwargs
            )
            return self.create(run)

    def get_latest_run(
        self,
        raw_repo_id: ObjectId,
    ) -> Optional[RawWorkflowRun]:
        """Get the most recent workflow run for a repository."""
        doc = (
            self.collection.find({"raw_repo_id": raw_repo_id})
            .sort("build_created_at", -1)
            .limit(1)
        )
        docs = list(doc)
        return RawWorkflowRun(**docs[0]) if docs else None

    def count_by_repo(self, raw_repo_id: ObjectId) -> int:
        """Count workflow runs for a repository."""
        return self.collection.count_documents({"raw_repo_id": raw_repo_id})
