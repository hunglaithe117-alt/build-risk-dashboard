"""
Monitoring Service - Gathers system stats from Celery, Redis, MongoDB.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis
from pymongo.database import Database

from app.config import settings
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service to gather system monitoring stats."""

    def __init__(self, db: Database):
        self.db = db
        self._redis_client: Optional[redis.Redis] = None

    @property
    def redis_client(self) -> redis.Redis:
        if self._redis_client is None:
            self._redis_client = redis.from_url(settings.REDIS_URL)
        return self._redis_client

    def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system stats."""
        return {
            "celery": self._get_celery_stats(),
            "redis": self._get_redis_stats(),
            "mongodb": self._get_mongodb_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _get_celery_stats(self) -> Dict[str, Any]:
        """Get Celery worker and queue stats."""
        try:
            inspect = celery_app.control.inspect(timeout=2.0)

            # Get active workers
            active = inspect.active() or {}
            reserved = inspect.reserved() or {}
            stats = inspect.stats() or {}

            workers = []
            for worker_name, worker_stats in stats.items():
                active_tasks = len(active.get(worker_name, []))
                reserved_tasks = len(reserved.get(worker_name, []))

                workers.append(
                    {
                        "name": worker_name,
                        "status": "online",
                        "active_tasks": active_tasks,
                        "reserved_tasks": reserved_tasks,
                        "processed": worker_stats.get("total", {}).get("app.tasks", 0),
                        "pool": worker_stats.get("pool", {}).get("max-concurrency", 0),
                    }
                )

            # Get queue lengths from Redis
            queues = self._get_queue_lengths()

            return {
                "workers": workers,
                "worker_count": len(workers),
                "queues": queues,
                "status": "online" if workers else "offline",
            }
        except Exception as e:
            logger.error(f"Failed to get Celery stats: {e}")
            return {
                "workers": [],
                "worker_count": 0,
                "queues": {},
                "status": "error",
                "error": str(e),
            }

    def _get_queue_lengths(self) -> Dict[str, int]:
        """Get message count for each Celery queue."""
        queue_names = ["default", "ingestion", "processing", "sonar_scan", "trivy_scan"]
        queues = {}

        try:
            for queue_name in queue_names:
                # Celery uses Redis lists for queues
                length = self.redis_client.llen(queue_name)
                queues[queue_name] = length
        except Exception as e:
            logger.error(f"Failed to get queue lengths: {e}")

        return queues

    def _get_redis_stats(self) -> Dict[str, Any]:
        """Get Redis server stats."""
        try:
            info = self.redis_client.info()
            return {
                "connected": True,
                "version": info.get("redis_version", "unknown"),
                "memory_used": info.get("used_memory_human", "0B"),
                "memory_peak": info.get("used_memory_peak_human", "0B"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_days": info.get("uptime_in_days", 0),
                "total_commands": info.get("total_commands_processed", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {e}")
            return {
                "connected": False,
                "error": str(e),
            }

    def _get_mongodb_stats(self) -> Dict[str, Any]:
        """Get MongoDB server stats."""
        try:
            # Get server status
            server_status = self.db.command("serverStatus")

            # Get collection names
            collections = self.db.list_collection_names()

            return {
                "connected": True,
                "version": server_status.get("version", "unknown"),
                "uptime_seconds": server_status.get("uptime", 0),
                "connections": {
                    "current": server_status.get("connections", {}).get("current", 0),
                    "available": server_status.get("connections", {}).get(
                        "available", 0
                    ),
                },
                "collections": len(collections),
                "operations": {
                    "insert": server_status.get("opcounters", {}).get("insert", 0),
                    "query": server_status.get("opcounters", {}).get("query", 0),
                    "update": server_status.get("opcounters", {}).get("update", 0),
                    "delete": server_status.get("opcounters", {}).get("delete", 0),
                },
            }
        except Exception as e:
            logger.error(f"Failed to get MongoDB stats: {e}")
            return {
                "connected": False,
                "error": str(e),
            }

    def get_pipeline_runs(
        self,
        limit: int = 50,
        skip: int = 0,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get recent Hamilton pipeline execution runs."""
        from app.repositories.pipeline_run import PipelineRunRepository

        repo = PipelineRunRepository(self.db)

        runs, total = repo.find_recent(
            limit=limit,
            skip=skip,
            status=status,
        )

        return {
            "runs": [
                {
                    "id": str(run.id),
                    "category": run.category,
                    "raw_repo_id": str(run.raw_repo_id),
                    "raw_build_run_id": str(run.raw_build_run_id),
                    "status": run.status,
                    "started_at": (
                        run.started_at.isoformat() if run.started_at else None
                    ),
                    "completed_at": (
                        run.completed_at.isoformat() if run.completed_at else None
                    ),
                    "duration_ms": run.duration_ms,
                    "feature_count": run.feature_count,
                    "nodes_executed": run.nodes_executed,
                    "nodes_succeeded": run.nodes_succeeded,
                    "nodes_failed": run.nodes_failed,
                    "errors": run.errors[:3] if run.errors else [],
                }
                for run in runs
            ],
            "total": total,
        }

    def get_pipeline_runs_cursor(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get pipeline runs with cursor-based pagination for infinite scroll."""
        from bson import ObjectId
        from app.repositories.pipeline_run import PipelineRunRepository

        repo = PipelineRunRepository(self.db)

        runs, next_cursor, has_more = repo.find_recent_cursor(
            limit=limit,
            cursor=cursor,
            status=status,
        )

        # Collect unique repo_ids and build_run_ids to batch lookup
        repo_ids = set()
        build_ids = set()
        for run in runs:
            repo_ids.add(run.raw_repo_id)
            build_ids.add(run.raw_build_run_id)

        # Batch lookup repositories
        repo_map: Dict[str, Dict[str, Any]] = {}
        if repo_ids:
            repos_cursor = self.db["raw_repositories"].find(
                {"_id": {"$in": [ObjectId(str(rid)) for rid in repo_ids]}},
                {"full_name": 1, "name": 1},
            )
            for r in repos_cursor:
                repo_map[str(r["_id"])] = {
                    "full_name": r.get("full_name", ""),
                    "name": r.get("name", ""),
                }

        # Batch lookup build runs
        build_map: Dict[str, Dict[str, Any]] = {}
        if build_ids:
            builds_cursor = self.db["raw_build_runs"].find(
                {"_id": {"$in": [ObjectId(str(bid)) for bid in build_ids]}},
                {"run_number": 1, "event": 1, "head_branch": 1, "workflow_name": 1},
            )
            for b in builds_cursor:
                build_map[str(b["_id"])] = {
                    "run_number": b.get("run_number"),
                    "event": b.get("event", ""),
                    "head_branch": b.get("head_branch", ""),
                    "workflow_name": b.get("workflow_name", ""),
                }

        return {
            "runs": [
                {
                    "id": str(run.id),
                    "category": run.category,
                    "raw_repo_id": str(run.raw_repo_id),
                    "raw_build_run_id": str(run.raw_build_run_id),
                    "repo": repo_map.get(str(run.raw_repo_id), {}),
                    "build": build_map.get(str(run.raw_build_run_id), {}),
                    "status": run.status,
                    "started_at": (
                        run.started_at.isoformat() if run.started_at else None
                    ),
                    "completed_at": (
                        run.completed_at.isoformat() if run.completed_at else None
                    ),
                    "duration_ms": run.duration_ms,
                    "feature_count": run.feature_count,
                    "nodes_executed": run.nodes_executed,
                    "nodes_succeeded": run.nodes_succeeded,
                    "nodes_failed": run.nodes_failed,
                    "errors": run.errors[:3] if run.errors else [],
                }
                for run in runs
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def get_background_jobs(self) -> Dict[str, Any]:
        """Get overview of all background jobs."""
        from app.repositories.export_job import ExportJobRepository
        from app.repositories.dataset_scan import DatasetScanRepository
        from app.repositories.dataset_version import DatasetVersionRepository

        export_repo = ExportJobRepository(self.db)
        scan_repo = DatasetScanRepository(self.db)
        version_repo = DatasetVersionRepository(self.db)

        # Get active export jobs
        active_exports = list(
            export_repo.collection.find(
                {"status": {"$in": ["pending", "processing"]}},
                sort=[("created_at", -1)],
                limit=10,
            )
        )

        # Get active scans
        active_scans = list(
            scan_repo.collection.find(
                {"status": {"$in": ["pending", "running", "partial"]}},
                sort=[("created_at", -1)],
                limit=10,
            )
        )

        # Get active enrichment versions
        active_enrichments = list(
            version_repo.collection.find(
                {"status": {"$in": ["pending", "processing"]}},
                sort=[("created_at", -1)],
                limit=10,
            )
        )

        return {
            "exports": [
                {
                    "id": str(j["_id"]),
                    "status": j.get("status"),
                    "format": j.get("format"),
                    "total_rows": j.get("total_rows", 0),
                    "processed_rows": j.get("processed_rows", 0),
                    "created_at": (
                        j.get("created_at").isoformat() if j.get("created_at") else None
                    ),
                }
                for j in active_exports
            ],
            "scans": [
                {
                    "id": str(s["_id"]),
                    "dataset_id": str(s.get("dataset_id")),
                    "tool_type": s.get("tool_type"),
                    "status": s.get("status"),
                    "total_commits": s.get("total_commits", 0),
                    "scanned_commits": s.get("scanned_commits", 0),
                    "created_at": (
                        s.get("created_at").isoformat() if s.get("created_at") else None
                    ),
                }
                for s in active_scans
            ],
            "enrichments": [
                {
                    "id": str(e["_id"]),
                    "dataset_id": str(e.get("dataset_id")),
                    "status": e.get("status"),
                    "total_rows": e.get("total_rows", 0),
                    "processed_rows": e.get("processed_rows", 0),
                    "created_at": (
                        e.get("created_at").isoformat() if e.get("created_at") else None
                    ),
                }
                for e in active_enrichments
            ],
            "summary": {
                "active_exports": len(active_exports),
                "active_scans": len(active_scans),
                "active_enrichments": len(active_enrichments),
            },
        }

    def get_system_logs(
        self,
        limit: int = 100,
        skip: int = 0,
        level: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get system logs from MongoDB 'system_logs' collection.

        Args:
            limit: Max number of logs to return
            skip: Pagination offset
            level: Filter by log level (DEBUG, INFO, WARNING, ERROR)
            source: Filter by source/component
        """
        collection = self.db["system_logs"]

        # Build filter
        query: Dict[str, Any] = {}
        if level:
            query["level"] = level.upper()
        if source:
            query["source"] = {"$regex": source, "$options": "i"}

        # Get total count
        total = collection.count_documents(query)

        # Get logs sorted by timestamp desc
        cursor = collection.find(query).sort("timestamp", -1).skip(skip).limit(limit)

        logs = []
        for doc in cursor:
            logs.append(
                {
                    "id": str(doc["_id"]),
                    "timestamp": (
                        doc.get("timestamp").isoformat()
                        if doc.get("timestamp")
                        else None
                    ),
                    "level": doc.get("level", "INFO"),
                    "source": doc.get("source", "unknown"),
                    "message": doc.get("message", ""),
                    "details": doc.get("details"),
                }
            )

        return {
            "logs": logs,
            "total": total,
            "has_more": skip + limit < total,
        }

    def get_logs_for_export(
        self,
        level: Optional[str] = None,
        source: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[Dict[str, Any]]:
        """
        Get logs for export with optional date filtering.
        """
        collection = self.db["system_logs"]

        query: Dict[str, Any] = {}
        if level:
            query["level"] = level.upper()
        if source:
            query["source"] = {"$regex": source, "$options": "i"}
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date

        cursor = collection.find(query).sort("timestamp", -1).limit(10000)

        logs = []
        for doc in cursor:
            logs.append(
                {
                    "timestamp": (
                        doc.get("timestamp").isoformat()
                        if doc.get("timestamp")
                        else None
                    ),
                    "level": doc.get("level", "INFO"),
                    "source": doc.get("source", "unknown"),
                    "message": doc.get("message", ""),
                    "details": doc.get("details"),
                }
            )

        return logs
