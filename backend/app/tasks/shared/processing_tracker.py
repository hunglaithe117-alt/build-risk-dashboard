"""
Processing Tracker - Track batch processing results using Redis.

Tracks extraction results per correlation_id for current processing batch:
- success_count, failed_count, skipped_count
- builds_for_prediction (list of build IDs ready for prediction)

TTL: 1 hour (auto cleanup)
"""

import logging
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class ProcessingTracker:
    """
    Track processing results per correlation_id using Redis.

    Usage:
        tracker = ProcessingTracker(redis_client, repo_config_id, correlation_id)
        tracker.record_success(build_id)  # After successful extraction
        tracker.record_failure(build_id)  # After failed extraction
        results = tracker.get_results()   # In finalize task
        tracker.cleanup()                 # After processing complete
    """

    TTL_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        redis_client: redis.Redis,
        repo_config_id: str,
        correlation_id: str,
    ):
        self.redis = redis_client
        self.repo_config_id = repo_config_id
        self.correlation_id = correlation_id
        self.key = f"processing:{repo_config_id}:{correlation_id}"
        self.prediction_key = f"{self.key}:prediction_ids"

    def record_success(self, build_id: str) -> None:
        """Record successful extraction, add build to prediction list."""
        try:
            pipe = self.redis.pipeline()
            pipe.hincrby(self.key, "success_count", 1)
            pipe.rpush(self.prediction_key, build_id)
            pipe.expire(self.key, self.TTL_SECONDS)
            pipe.expire(self.prediction_key, self.TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to record success for {build_id}: {e}")

    def record_failure(self, build_id: str, error: Optional[str] = None) -> None:
        """Record failed extraction."""
        try:
            pipe = self.redis.pipeline()
            pipe.hincrby(self.key, "failed_count", 1)
            pipe.expire(self.key, self.TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to record failure for {build_id}: {e}")

    def record_skipped(self, build_id: str, reason: Optional[str] = None) -> None:
        """Record skipped build (already processed)."""
        try:
            pipe = self.redis.pipeline()
            pipe.hincrby(self.key, "skipped_count", 1)
            pipe.expire(self.key, self.TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to record skip for {build_id}: {e}")

    def get_results(self) -> dict:
        """
        Get aggregated results for this processing batch.

        Returns:
            dict with keys:
            - success_count: int
            - failed_count: int
            - skipped_count: int
            - builds_for_prediction: List[str] (build IDs)
        """
        try:
            data = self.redis.hgetall(self.key)
            prediction_ids = self.redis.lrange(self.prediction_key, 0, -1)

            return {
                "success_count": int(data.get("success_count", 0)),
                "failed_count": int(data.get("failed_count", 0)),
                "skipped_count": int(data.get("skipped_count", 0)),
                "builds_for_prediction": prediction_ids,
            }
        except Exception as e:
            logger.error(f"Failed to get processing results: {e}")
            return {
                "success_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "builds_for_prediction": [],
            }

    def cleanup(self) -> None:
        """Delete tracking keys after processing completes."""
        try:
            self.redis.delete(self.key, self.prediction_key)
        except Exception as e:
            logger.warning(f"Failed to cleanup processing tracker keys: {e}")

    def initialize(self, total_builds: int) -> None:
        """Initialize tracker with total builds count (optional)."""
        try:
            pipe = self.redis.pipeline()
            pipe.hset(self.key, "total_builds", total_builds)
            pipe.hset(self.key, "success_count", 0)
            pipe.hset(self.key, "failed_count", 0)
            pipe.hset(self.key, "skipped_count", 0)
            pipe.expire(self.key, self.TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to initialize processing tracker: {e}")
