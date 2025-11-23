from typing import Any, Dict, List, Optional
from datetime import datetime

from pymongo.database import Database

from app.models.entities.workflow_run import WorkflowRunRaw
from .base import BaseRepository


class WorkflowRunRepository(BaseRepository[WorkflowRunRaw]):
    def __init__(self, db: Database):
        super().__init__(db, "workflow_runs", WorkflowRunRaw)

    def find_by_repo_and_run_id(
        self, repo_id: str, workflow_run_id: int
    ) -> Optional[WorkflowRunRaw]:
        return self.find_one(
            {"repo_id": self._to_object_id(repo_id), "workflow_run_id": workflow_run_id}
        )

    def list_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 0
    ) -> tuple[List[WorkflowRunRaw], int]:
        return self.paginate(
            {"repo_id": self._to_object_id(repo_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_in_date_range(
        self, repo_id: str, start_date: datetime, end_date: datetime
    ) -> List[WorkflowRunRaw]:
        """Find workflow runs within a specific time window."""
        query = {
            "repo_id": self._to_object_id(repo_id),
            "created_at": {"$gte": start_date, "$lte": end_date},
        }
        return self.find_many(query)
