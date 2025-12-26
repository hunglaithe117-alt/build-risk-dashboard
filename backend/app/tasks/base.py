"""
Base Celery Task with automatic TracingContext propagation.

All PipelineTask subclasses automatically:
1. Restore TracingContext from `correlation_id` kwarg (if present)
2. Set task_name from the Celery task name
3. Clear TracingContext on task completion
4. Auto-retry on GithubAllRateLimitError with EXACT countdown from retry_after
5. Send notification when all GitHub tokens are exhausted

Note: GithubRateLimitError is handled internally by GitHubClient via token rotation.
Only GithubAllRateLimitError (when ALL tokens exhausted) is propagated to tasks.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from pymongo.database import Database

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

    def __call__(self, *args, **kwargs):
        """
        Override __call__ to handle GithubAllRateLimitError with exact countdown.

        When all tokens are exhausted (GithubAllRateLimitError), retry with the
        EXACT countdown from retry_after instead of exponential backoff.
        """
        try:
            return super().__call__(*args, **kwargs)
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

    def _calculate_countdown(self, exc: GithubAllRateLimitError) -> int | None:
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

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_database()
        return self._db

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover - logging only
        """Handle task failure - log error and send notification for rate limit exhaustion."""
        logger.error("Task %s failed: %s", self.name, exc, exc_info=exc)

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
