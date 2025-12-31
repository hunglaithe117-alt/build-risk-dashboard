"""
Base Celery Task with automatic TracingContext propagation.

All PipelineTask subclasses automatically:
1. Restore TracingContext from `correlation_id` kwarg (if present)
2. Set task_name from the Celery task name
3. Clear TracingContext on task completion
4. Auto-retry on GithubAllRateLimitError with EXACT countdown from retry_after
5. Send notification when all GitHub tokens are exhausted
6. Handle SoftTimeLimitExceeded to update entity status before failing

Note: GithubRateLimitError is handled internally by GitHubClient via token rotation.
Only GithubAllRateLimitError (when ALL tokens exhausted) is propagated to tasks.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import redis
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from pymongo.database import Database

from app.config import settings
from app.core.tracing import TracingContext
from app.database.mongo import get_database
from app.services.github.exceptions import (
    GithubAllRateLimitError,
    GithubRetryableError,
)

logger = logging.getLogger(__name__)


class PipelineTask(Task):
    """
    Base task with automatic database connection and TracingContext propagation.

    TracingContext fields are automatically restored from task kwargs:
    - correlation_id: Restored from `correlation_id` kwarg
    - dataset_id: Restored from `dataset_id` kwarg
    - version_id: Restored from `version_id` kwarg
    - repo_id: Restored from `repo_id` or `repo_config_id` kwarg
    - task_name: Set from the Celery task name

    Rate Limit Handling:
    - GithubAllRateLimitError: Auto-retry with EXACT countdown when all tokens exhausted
    - Sends notification when all tokens are exhausted (after max retries)
    """

    abstract = True
    # GithubRetryableError uses standard exponential backoff
    autoretry_for = (GithubRetryableError,)
    retry_backoff = True
    retry_backoff_max = 3600  # 1 hour max for exponential backoff
    retry_kwargs = {"max_retries": 3}
    default_retry_delay = 10

    def __init__(self) -> None:
        self._db: Database | None = None
        self._redis: redis.Redis | None = None

    def __call__(self, *args, **kwargs):
        """
        Override __call__ to handle special exceptions.

        Handles:
        - GithubAllRateLimitError: Retry with EXACT countdown from retry_after
        - SoftTimeLimitExceeded: Update entity status to FAILED before re-raising
        """
        try:
            return super().__call__(*args, **kwargs)
        except SoftTimeLimitExceeded:
            # Task exceeded time limit - update entity status before failing
            logger.error(f"Task {self.name} exceeded soft time limit, marking entity as failed")
            self._handle_entity_failure(
                kwargs,
                "Task exceeded time limit. Network may be slow or data is too large. Please retry.",
            )
            raise
        except GithubAllRateLimitError as exc:
            # All tokens exhausted - calculate exact countdown from retry_after
            countdown = self._calculate_countdown(exc)

            if countdown is not None:
                logger.warning(
                    f"All tokens exhausted for task {self.name}, "
                    f"retrying in {countdown}s (exact countdown from retry_after)"
                )
                raise self.retry(exc=exc, countdown=countdown) from exc
            else:
                # No retry_after available, use default delay
                logger.warning(
                    f"All tokens exhausted for task {self.name}, "
                    f"retrying with default delay (no retry_after available)"
                )
                raise self.retry(exc=exc, countdown=self.default_retry_delay) from exc

    def _calculate_countdown(self, exc: GithubAllRateLimitError) -> Optional[int]:
        """
        Calculate exact countdown seconds from exception's retry_after.

        Args:
            exc: GithubAllRateLimitError with retry_after attribute

        Returns:
            Countdown in seconds, or None if retry_after is not available
        """
        retry_after = getattr(exc, "retry_after", None)

        if retry_after is None:
            return None

        # retry_after can be int/float (seconds) or datetime
        if isinstance(retry_after, (int, float)):
            return max(1, int(retry_after) + 5)
        elif isinstance(retry_after, datetime):
            now = datetime.now(timezone.utc)
            delta = (retry_after - now).total_seconds()
            return max(1, int(delta) + 5)

        return None

    def before_start(self, task_id: str, args: tuple, kwargs: dict):  # pragma: no cover
        """
        Called before task execution - restore TracingContext from kwargs.

        Automatically extracts tracing fields from task kwargs:
        - correlation_id -> TracingContext.correlation_id
        - dataset_id -> TracingContext.dataset_id
        - version_id -> TracingContext.version_id
        - repo_id/repo_config_id -> TracingContext.repo_id
        """
        # Extract tracing context from kwargs (don't pop - task may need them)
        correlation_id = kwargs.get("correlation_id", "")
        dataset_id = kwargs.get("dataset_id", "")
        version_id = kwargs.get("version_id", "")
        repo_id = kwargs.get("repo_id", "") or kwargs.get("repo_config_id", "")

        # Extract task short name (last part of dotted name)
        task_short_name = self.name.split(".")[-1] if self.name else ""

        # Only set context if at least correlation_id is present
        if correlation_id:
            TracingContext.set(
                correlation_id=correlation_id,
                dataset_id=dataset_id,
                version_id=version_id,
                repo_id=repo_id,
                task_name=task_short_name,
            )

    def after_return(
        self, status: str, retval: Any, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover
        """Called after task completion - clear database and TracingContext."""
        if self._db is not None:
            # PyMongo handles pooling; no need to close. Clear cache to avoid holding references.
            self._db = None

        # Clear tracing context to avoid leaking to other tasks
        TracingContext.clear()

        # Close Redis connection if it exists
        if self._redis:
            self._redis.close()
            self._redis = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_database()
        return self._db

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    def get_entity_failure_handler(self, kwargs: dict) -> Optional[Callable[[str, str], None]]:
        """
        Override in subclass to provide entity status updater on task failure.

        When a task fails (timeout, unhandled exception, etc.), this handler
        is called to update the associated entity's status to FAILED.

        Args:
            kwargs: Task keyword arguments (contains dataset_id, version_id, etc.)

        Returns:
            Callable that takes (status: str, error_message: str) to update entity,
            or None if no entity update is needed.

        Example subclass implementation:
            def get_entity_failure_handler(self, kwargs):
                dataset_id = kwargs.get("dataset_id")
                if not dataset_id:
                    return None
                def updater(status, error_msg):
                    dataset_repo = DatasetRepository(self.db)
                    dataset_repo.update_one(dataset_id, {
                        "validation_status": status,
                        "validation_error": error_msg,
                    })
                return updater
        """
        return None

    def _handle_entity_failure(self, kwargs: dict, error_message: str) -> None:
        """
        Call entity failure handler to update entity status.

        Safe to call - catches exceptions to prevent masking the original error.
        """
        try:
            handler = self.get_entity_failure_handler(kwargs)
            if handler:
                handler("failed", error_message)
                logger.info(f"Entity status updated to 'failed' for task {self.name}")
        except Exception as e:
            # Log but don't raise - we don't want to mask the original error
            logger.warning(f"Failed to update entity status: {e}")

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover - logging only
        """
        Handle task failure.

        Actions:
        1. Log the error
        2. Update entity status to FAILED (via get_entity_failure_handler)
        3. Send notification for rate limit exhaustion
        """
        logger.error("Task %s failed: %s", self.name, exc, exc_info=exc)

        # Update entity status to FAILED (unless already handled by __call__)
        if not isinstance(exc, SoftTimeLimitExceeded):
            self._handle_entity_failure(kwargs, str(exc))

        # Send notification when all GitHub tokens are exhausted (after max retries)
        if isinstance(exc, GithubAllRateLimitError):
            self._notify_rate_limit_exhausted(exc)

    def _notify_rate_limit_exhausted(self, exc: GithubAllRateLimitError) -> None:
        """Send notification when all GitHub tokens are exhausted."""
        try:
            from app.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)
            notification_service.notify_rate_limit_exhausted(
                retry_after=exc.retry_after,
                task_name=self.name,
            )
            logger.warning(
                f"All GitHub tokens exhausted. Task {self.name} failed after max retries. "
                f"Tokens will reset at: {exc.retry_after}"
            )
        except Exception as notify_exc:
            # Don't fail the task if notification fails
            logger.warning(f"Failed to send rate limit notification: {notify_exc}")


class ModelPipelineTask(PipelineTask):
    """
    Pipeline task for ModelRepoConfig with automatic failure handling.

    When any unhandled exception occurs (including SoftTimeLimitExceeded),
    this task will automatically:
    1. Update ModelRepoConfig status to FAILED
    2. Log the error with correlation_id for traceability
    3. Send WebSocket notification to frontend
    4. Store error_message for user visibility

    Usage:
        @celery_app.task(bind=True, base=ModelPipelineTask, ...)
        def my_task(self, repo_config_id: str, ...):
            ...

    Note: Only critical/unrecoverable exceptions will set FAILED status.
    Individual build failures are tracked at ModelTrainingBuild level.
    """

    abstract = True

    def get_entity_failure_handler(self, kwargs: dict):
        """
        Override to auto-update ModelRepoConfig status to FAILED on task failure.

        Extracts repo_config_id from kwargs and returns an updater function.
        """
        repo_config_id = kwargs.get("repo_config_id")
        if not repo_config_id:
            return None

        # Capture correlation_id for logging
        correlation_id = kwargs.get("correlation_id", "unknown")

        def updater(status: str, error_msg: str) -> None:
            """Update ModelRepoConfig to FAILED status with error details."""
            from app.entities.model_repo_config import ModelImportStatus
            from app.repositories.model_repo_config import ModelRepoConfigRepository
            from app.tasks.shared.status_publisher import publish_status

            log_prefix = f"[corr={correlation_id[:8] if correlation_id != 'unknown' else 'N/A'}]"

            try:
                # Truncate error message for storage
                truncated_error = error_msg[:500] if error_msg else "Unknown error"

                # Update repo config status
                repo_config_repo = ModelRepoConfigRepository(self.db)
                repo_config_repo.update_repository(
                    repo_config_id,
                    {
                        "status": ModelImportStatus.FAILED.value,
                        "error_message": truncated_error,
                    },
                )

                # Log with correlation_id for traceability
                logger.error(
                    f"{log_prefix} ModelRepoConfig {repo_config_id} marked as FAILED. "
                    f"Task: {self.name}. Error: {truncated_error[:200]}"
                )

                # Notify frontend via WebSocket
                publish_status(
                    repo_config_id,
                    "failed",
                    f"Pipeline failed: {truncated_error[:200]}",
                )

            except Exception as update_exc:
                # Log but don't raise - we don't want to mask the original error
                logger.warning(
                    f"{log_prefix} Failed to update ModelRepoConfig {repo_config_id} "
                    f"to FAILED status: {update_exc}"
                )

        return updater
