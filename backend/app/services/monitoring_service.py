"""
Monitoring Service - Gathers system stats from Celery, Redis, MongoDB.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis
from pymongo.database import Database

from app.celery_app import celery_app
from app.config import settings
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.repositories.system_log import SystemLogRepository

logger = logging.getLogger(__name__)


class MonitoringService:
    """Service to gather system monitoring stats."""

    def __init__(self, db: Database):
        self.db = db
        self._redis_client: Optional[redis.Redis] = None
        self._raw_build_run_repo = RawBuildRunRepository(db)
        self._raw_repo_repo = RawRepositoryRepository(db)
        self._system_log_repo = SystemLogRepository(db)

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
            "trivy": self._get_trivy_stats(),
            "sonarqube": self._get_sonarqube_stats(),
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

    def _get_trivy_stats(self) -> Dict[str, Any]:
        """Get Trivy tool health status."""
        try:
            from app.integrations.tools.trivy import TrivyTool

            tool = TrivyTool()
            return tool.get_health_status()
        except Exception as e:
            logger.error(f"Failed to get Trivy stats: {e}")
            return {
                "connected": False,
                "error": str(e),
            }

    def _get_sonarqube_stats(self) -> Dict[str, Any]:
        """Get SonarQube tool health status."""
        try:
            from app.integrations.tools.sonarqube import SonarQubeTool

            tool = SonarQubeTool()
            return tool.get_health_status()
        except Exception as e:
            logger.error(f"Failed to get SonarQube stats: {e}")
            return {
                "connected": False,
                "error": str(e),
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
        logs, total = self._system_log_repo.find_recent(
            skip=skip,
            limit=limit,
            level=level,
            source=source,
        )

        return {
            "logs": [
                {
                    "id": str(log.id),
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "level": log.level,
                    "source": log.source,
                    "message": log.message,
                    "details": log.details,
                }
                for log in logs
            ],
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
        logs = self._system_log_repo.find_for_export(
            level=level,
            source=source,
            start_date=start_date,
            end_date=end_date,
        )

        return [
            {
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "level": log.level,
                "source": log.source,
                "message": log.message,
                "details": log.details,
            }
            for log in logs
        ]

    def stream_logs_export(
        self,
        format: str = "csv",
        level: Optional[str] = None,
        source: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
        """
        Stream logs export as CSV or JSON.

        Args:
            format: "csv" or "json"
            level: Filter by log level
            source: Filter by source/component
            start_date: Filter by timestamp >= start_date
            end_date: Filter by timestamp <= end_date

        Returns:
            Generator yielding CSV/JSON chunks
        """
        from app.utils.export_utils import format_log_row, stream_csv, stream_json

        cursor = self._system_log_repo.get_cursor_for_export(
            level=level,
            source=source,
            start_date=start_date,
            end_date=end_date,
        )

        if format == "csv":
            return stream_csv(cursor, format_log_row)
        else:
            return stream_json(cursor, format_log_row)

    def get_log_metrics(
        self,
        hours: int = 24,
        bucket_minutes: int = 60,
    ) -> Dict[str, Any]:
        """
        Get log count metrics aggregated by time bucket and level.

        Used for metrics charts on the monitoring dashboard.

        Args:
            hours: Number of hours to look back (default 24)
            bucket_minutes: Size of each time bucket in minutes (default 60)

        Returns:
            Dict with time_buckets array and level_counts
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        # Aggregation pipeline to bucket logs by time and level
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_time}}},
            {
                "$group": {
                    "_id": {
                        "bucket": {
                            "$dateTrunc": {
                                "date": "$timestamp",
                                "unit": "minute",
                                "binSize": bucket_minutes,
                            }
                        },
                        "level": "$level",
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.bucket": 1}},
        ]

        results = list(self._system_log_repo.aggregate(pipeline))

        # Transform results into chart-friendly format
        buckets_dict: Dict[str, Dict[str, int]] = {}
        for r in results:
            bucket_time = r["_id"]["bucket"].isoformat()
            level = r["_id"]["level"]
            count = r["count"]

            if bucket_time not in buckets_dict:
                buckets_dict[bucket_time] = {
                    "timestamp": bucket_time,
                    "ERROR": 0,
                    "WARNING": 0,
                    "INFO": 0,
                    "DEBUG": 0,
                }
            buckets_dict[bucket_time][level] = count

        # Sort by timestamp and return as array
        time_buckets = sorted(buckets_dict.values(), key=lambda x: x["timestamp"])

        # Calculate totals
        level_totals = {"ERROR": 0, "WARNING": 0, "INFO": 0, "DEBUG": 0}
        for bucket in time_buckets:
            for level in level_totals:
                level_totals[level] += bucket.get(level, 0)

        return {
            "time_buckets": time_buckets,
            "level_totals": level_totals,
            "hours": hours,
            "bucket_minutes": bucket_minutes,
        }
