"""
Maintenance Tasks - Scheduled cleanup and housekeeping jobs.

These tasks are designed to run periodically via Celery Beat.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from celery import shared_task

from app.database.mongo import get_database
from app.repositories.pipeline_run import PipelineRunRepository

logger = logging.getLogger(__name__)


@shared_task(
    name="app.tasks.maintenance.cleanup_pipeline_runs",
    bind=True,
    queue="data_processing",
)
def cleanup_pipeline_runs(self, days: int = 30) -> Dict[str, Any]:
    """
    Clean up old pipeline runs to free up storage.

    This task is designed to run daily via Celery Beat.
    It deletes pipeline run records older than the specified number of days.

    Args:
        days: Number of days to keep. Runs older than this will be deleted.

    Returns:
        Dict with deleted count and timestamp.
    """
    db = get_database()
    repo = PipelineRunRepository(db)

    try:
        deleted_count = repo.cleanup_old_runs(days=days)
        
        logger.info(
            f"Pipeline runs cleanup completed: deleted {deleted_count} runs older than {days} days"
        )

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "days_threshold": days,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Pipeline runs cleanup failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


@shared_task(
    name="app.tasks.maintenance.cleanup_failed_scans",
    bind=True,
    queue="data_processing",
)
def cleanup_failed_scans(self, days: int = 90) -> Dict[str, Any]:
    """
    Clean up old failed scan records that have been resolved.

    Args:
        days: Number of days to keep resolved failed scans.

    Returns:
        Dict with deleted count and timestamp.
    """
    from app.repositories.failed_scan import FailedScanRepository
    from datetime import timedelta

    db = get_database()
    repo = FailedScanRepository(db)

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Only delete resolved failed scans older than threshold
        result = repo.collection.delete_many({
            "resolved_at": {"$lt": cutoff},
            "status": "resolved",
        })
        
        deleted_count = result.deleted_count
        
        logger.info(
            f"Failed scans cleanup completed: deleted {deleted_count} resolved scans older than {days} days"
        )

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "days_threshold": days,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed scans cleanup failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }


@shared_task(
    name="app.tasks.maintenance.refresh_token_pool",
    bind=True,
    queue="data_processing",
)
def refresh_token_pool(self) -> Dict[str, Any]:
    """
    Refresh the Redis token pool from MongoDB.

    This ensures any newly added tokens are available in the pool.
    Also cleans up any invalid or deleted tokens from the pool.

    Returns:
        Dict with synced count and timestamp.
    """
    try:
        from app.services.github.redis_token_pool import get_redis_token_pool

        db = get_database()
        pool = get_redis_token_pool(db)
        synced = pool.sync_from_mongodb(db)

        logger.info(f"Token pool refreshed: {synced} tokens synced")

        return {
            "status": "success",
            "tokens_synced": synced,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Token pool refresh failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
