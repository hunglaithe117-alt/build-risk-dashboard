"""
Pipeline Run Repository - CRUD operations for pipeline execution history.

Provides methods for:
- Tracking pipeline runs
- Querying execution history
- Aggregating statistics
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.pipeline_run import PipelineRun
from .base import BaseRepository


class PipelineRunRepository(BaseRepository[PipelineRun]):
    """Repository for pipeline execution history."""

    def __init__(self, db: Database):
        super().__init__(db, "pipeline_runs", PipelineRun)

    def find_by_build(self, build_sample_id: str) -> List[PipelineRun]:
        """Find all pipeline runs for a specific build sample."""
        return self.find_many(
            {"build_sample_id": self._to_object_id(build_sample_id)},
            sort=[("created_at", -1)],
        )

    def find_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[List[PipelineRun], int]:
        """Find pipeline runs for a repository with pagination."""
        return self.paginate(
            {"repo_id": self._to_object_id(repo_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_recent(self, limit: int = 100) -> List[PipelineRun]:
        """Find most recent pipeline runs across all repos."""
        return self.find_many({}, sort=[("created_at", -1)], limit=limit)

    def find_failed(self, since: Optional[datetime] = None) -> List[PipelineRun]:
        """Find failed pipeline runs, optionally since a specific time."""
        query: Dict[str, Any] = {"status": "failed"}
        if since:
            query["created_at"] = {"$gte": since}
        return self.find_many(query, sort=[("created_at", -1)])

    def find_running(self) -> List[PipelineRun]:
        """Find currently running pipeline runs."""
        return self.find_many({"status": "running"}, sort=[("started_at", -1)])

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get aggregated pipeline statistics.

        Returns:
            Dict with success_rate, avg_duration, total_runs, etc.
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)

        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": None,
                    "total_runs": {"$sum": 1},
                    "completed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "failed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                    "total_features": {"$sum": "$feature_count"},
                    "total_retries": {"$sum": "$total_retries"},
                    "avg_nodes_executed": {"$avg": "$nodes_executed"},
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))
        if not results:
            return {
                "total_runs": 0,
                "completed": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "total_features": 0,
                "total_retries": 0,
                "avg_nodes_executed": 0.0,
                "period_days": days,
            }

        stats = results[0]
        total = stats["total_runs"]
        stats["success_rate"] = (stats["completed"] / total * 100) if total > 0 else 0.0
        stats["period_days"] = days
        del stats["_id"]
        return stats

    def get_stats_by_repo(self, repo_id: str) -> Dict[str, Any]:
        """Get statistics for a specific repository."""
        pipeline = [
            {"$match": {"repo_id": self._to_object_id(repo_id)}},
            {
                "$group": {
                    "_id": None,
                    "total_runs": {"$sum": 1},
                    "completed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "failed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                    "total_features": {"$sum": "$feature_count"},
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))
        if not results:
            return {
                "total_runs": 0,
                "completed": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "total_features": 0,
            }

        stats = results[0]
        total = stats["total_runs"]
        stats["success_rate"] = (stats["completed"] / total * 100) if total > 0 else 0.0
        del stats["_id"]
        return stats

    def cleanup_old_runs(self, days: int = 30) -> int:
        """Delete pipeline runs older than specified days. Returns count deleted."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.collection.delete_many({"created_at": {"$lt": cutoff}})
        return result.deleted_count
