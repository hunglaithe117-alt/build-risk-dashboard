"""
Pipeline Run Repository - Database operations for pipeline execution tracking.
"""

from typing import Any, Dict, List, Optional, Tuple

from .base import BaseRepository
from app.entities.pipeline_run import PipelineRun


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repository for PipelineRun entities."""

    def __init__(self, db):
        super().__init__(db, "pipeline_runs", PipelineRun)

    def find_recent(
        self,
        limit: int = 50,
        skip: int = 0,
        status: Optional[str] = None,
    ) -> Tuple[List[PipelineRun], int]:
        """
        Find recent pipeline runs with optional status filter.

        Args:
            limit: Maximum number of runs to return
            skip: Number of runs to skip (for pagination)
            status: Optional status filter

        Returns:
            Tuple of (list of runs, total count)
        """
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status

        return self.paginate(
            query,
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_by_repo(
        self,
        repo_id: str,
        limit: int = 20,
    ) -> List[PipelineRun]:
        """Find recent runs for a specific repository."""
        return self.find_many(
            {"repo_id": self._to_object_id(repo_id)},
            sort=[("created_at", -1)],
            limit=limit,
        )

    def find_by_build_sample(self, build_sample_id: str) -> Optional[PipelineRun]:
        """Find a run by build sample ID."""
        return self.find_one({"build_sample_id": self._to_object_id(build_sample_id)})

    def find_recent_cursor(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[PipelineRun], Optional[str], bool]:
        """
        Find recent pipeline runs with cursor-based pagination.

        Args:
            limit: Maximum number of runs to return
            cursor: Last item ID from previous page (fetch items older than this)
            status: Optional status filter

        Returns:
            Tuple of (list of runs, next_cursor, has_more)
        """
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status

        # If cursor provided, get items with _id less than cursor (older)
        if cursor:
            query["_id"] = {"$lt": self._to_object_id(cursor)}

        # Fetch limit + 1 to check if there are more items
        runs = self.find_many(
            query,
            sort=[("_id", -1)],  # Sort by _id descending (newest first)
            limit=limit + 1,
        )

        has_more = len(runs) > limit
        if has_more:
            runs = runs[:limit]  # Remove the extra item

        next_cursor = str(runs[-1].id) if runs and has_more else None

        return runs, next_cursor, has_more
