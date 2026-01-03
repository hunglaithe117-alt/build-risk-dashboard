"""
Base Celery Task with automatic TracingContext propagation and SafeTask pattern.

Task Hierarchy:
1. PipelineTask - Base with DB, Redis, TracingContext, rate limit handling
2. SafeTask - Adds run_safe() with error taxonomy and checkpoint/cleanup hooks

Error Taxonomy:
- TransientError: Retryable (network, timeout, API 429)
- PermanentError: Non-retryable (bad input, schema error)
- MissingResourceError: Expected missing (logs 404) - marks MISSING_RESOURCE

All tasks should catch SoftTimeLimitExceeded and convert to TransientError for retry.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import redis
from celery import Task
from celery.exceptions import Retry, SoftTimeLimitExceeded
from pymongo.database import Database

from app.config import settings
from app.core.tracing import TracingContext
from app.database.mongo import get_database
from app.services.github.exceptions import (
    GithubAllRateLimitError,
    GithubRetryableError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Error Taxonomy
# =============================================================================


class TransientError(Exception):
    """
    Retryable error: network glitch, timeout, API 429, temporary outage.

    SafeTask will checkpoint state, cleanup, and retry with exponential backoff.
    """


class PermanentError(Exception):
    """
    Non-retryable error: bad input, schema mismatch, deterministic failure.

    SafeTask will mark job as FAILED and NOT retry.
    """


class MissingResourceError(PermanentError):
    """
    Expected missing resource: logs expired (404), commit not found (squash merge).

    SafeTask will mark as MISSING_RESOURCE (not FAILED) - no retry needed.
    This is different from PermanentError because it's expected, not an error.
    """


# =============================================================================
# Task State for Checkpointing
# =============================================================================


@dataclass
class TaskState:
    """
    State for checkpoint/resume pattern.

    Tasks can use this to track progress through phases and resume after retry.
    """

    phase: str = "START"
    meta: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Backoff Helper
# =============================================================================


def compute_backoff(
    attempt: int,
    *,
    base: int = 5,
    cap: int = 300,
    jitter: bool = True,
) -> int:
    """
    Compute exponential backoff with jitter.

    Args:
        attempt: Current retry attempt (0-indexed)
        base: Base delay in seconds
        cap: Maximum delay in seconds
        jitter: Add randomness to prevent thundering herd

    Returns:
        Delay in seconds
    """
    delay = min(cap, base * (2**attempt))
    if jitter:
        delay = int(delay * (0.7 + 0.6 * random.random()))  # 0.7x..1.3x
    return max(1, delay)


# =============================================================================
# PipelineTask - Base Task
# =============================================================================


class PipelineTask(Task):
    """
    Base task with automatic database connection and TracingContext propagation.

    Provides:
    - Database connection (self.db)
    - Redis connection (self.redis)
    - TracingContext restoration from kwargs
    - GithubAllRateLimitError handling with exact countdown
    """

    abstract = True
    autoretry_for = (GithubRetryableError,)
    retry_backoff = True
    retry_backoff_max = 3600  # 1 hour max
    retry_kwargs = {"max_retries": 3}
    default_retry_delay = 10

    def __init__(self) -> None:
        self._db: Database | None = None
        self._redis: redis.Redis | None = None

    def __call__(self, *args, **kwargs):
        """Handle GithubAllRateLimitError with exact countdown."""
        try:
            return super().__call__(*args, **kwargs)
        except GithubAllRateLimitError as exc:
            countdown = self._calculate_countdown(exc)
            if countdown:
                logger.warning(f"All tokens exhausted for {self.name}, retrying in {countdown}s")
                raise self.retry(exc=exc, countdown=countdown) from exc
            else:
                raise self.retry(exc=exc, countdown=self.default_retry_delay) from exc

    def _calculate_countdown(self, exc: GithubAllRateLimitError) -> Optional[int]:
        """Calculate countdown from retry_after."""
        retry_after = getattr(exc, "retry_after", None)
        if retry_after is None:
            return None
        if isinstance(retry_after, (int, float)):
            return max(1, int(retry_after) + 5)
        elif isinstance(retry_after, datetime):
            now = datetime.now(timezone.utc)
            delta = (retry_after - now).total_seconds()
            return max(1, int(delta) + 5)
        return None

    def before_start(self, task_id: str, args: tuple, kwargs: dict):
        """Restore TracingContext from kwargs."""
        correlation_id = kwargs.get("correlation_id", "")
        dataset_id = kwargs.get("dataset_id", "")
        version_id = kwargs.get("version_id", "")
        repo_id = kwargs.get("repo_id", "") or kwargs.get("repo_config_id", "")
        task_short_name = self.name.split(".")[-1] if self.name else ""

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
    ):
        """Clear database and TracingContext after completion."""
        if self._db is not None:
            self._db = None
        TracingContext.clear()
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

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo):
        """Log failure and notify for rate limit exhaustion."""
        logger.error("Task %s failed: %s", self.name, exc, exc_info=exc)
        if isinstance(exc, GithubAllRateLimitError):
            self._notify_rate_limit_exhausted(exc)

    def _notify_rate_limit_exhausted(self, exc: GithubAllRateLimitError) -> None:
        """Send notification when all GitHub tokens exhausted."""
        try:
            from app.services.notification_service import NotificationService

            notification_service = NotificationService(self.db)
            retry_after = exc.retry_after
            if isinstance(retry_after, (int, float)):
                retry_after = datetime.fromtimestamp(retry_after, tz=timezone.utc)
            notification_service.notify_rate_limit_exhausted(
                retry_after=retry_after,
                task_name=self.name,
            )
        except Exception as notify_exc:
            logger.warning(f"Failed to send rate limit notification: {notify_exc}")


# =============================================================================
# SafeTask - Task with run_safe() Pattern
# =============================================================================


class SafeTask(PipelineTask):
    """
    Task with standardized error handling via run_safe().

    Behavior:
    - SoftTimeLimitExceeded: checkpoint + cleanup + retry
    - TransientError: checkpoint + cleanup + retry (exponential backoff)
    - Retry: re-raise (avoid double-handle)
    - MissingResourceError: mark MISSING_RESOURCE + cleanup + raise (no retry)
    - PermanentError: mark FAILED + cleanup + raise (no retry)
    - Other Exception: mark FAILED + cleanup + raise (configurable)

    Usage:
        @celery_app.task(bind=True, base=SafeTask, ...)
        def my_task(self, job_id: str, ...):
            def _work(state: TaskState) -> dict:
                if state.phase == "START":
                    # do work
                    state.phase = "DONE"
                return {"result": "ok"}

            return self.run_safe(
                job_id=job_id,
                work=_work,
                save_state_fn=lambda s: my_repo.save_state(job_id, s),
                mark_failed_fn=lambda e: my_repo.mark_failed(job_id, str(e)),
                cleanup_fn=lambda s: cleanup_partial_work(job_id, s),
            )
    """

    abstract = True

    # Disable Celery's autoretry - run_safe() handles retry logic
    # This prevents conflict where Celery auto-retries before run_safe() can checkpoint
    autoretry_for = ()

    max_retries = 5
    soft_retry_delay = 15
    transient_retry_base = 5
    transient_retry_cap = 300

    def run_safe(
        self,
        job_id: str,
        work: Callable[[TaskState], Any],
        *,
        load_state_fn: Callable[[str], TaskState] | None = None,
        save_state_fn: Callable[[TaskState], None] | None = None,
        mark_failed_fn: Callable[[Exception], None] | None = None,
        mark_missing_fn: Callable[[Exception], None] | None = None,
        cleanup_fn: Callable[[TaskState], None] | None = None,
        fail_on_unknown: bool = True,
    ) -> Any:
        """
        Execute work with standardized error handling.

        Args:
            job_id: Unique identifier for logging/tracing
            work: Work function that takes TaskState and returns result
            load_state_fn: Optional fn to load TaskState from DB
            save_state_fn: Optional fn to save TaskState to DB
            mark_failed_fn: Optional fn to mark job as FAILED in DB
            mark_missing_fn: Optional fn to mark job as MISSING_RESOURCE in DB
            cleanup_fn: Optional fn to cleanup partial work (MUST be idempotent)
            fail_on_unknown: If True, unknown exceptions mark FAILED. If False, retry.

        Returns:
            Result from work function
        """
        task_name = self.name or self.__class__.__name__
        log_prefix = f"[{task_name}][{job_id[:8] if len(job_id) >= 8 else job_id}]"

        # Load or create state
        if load_state_fn:
            state = load_state_fn(job_id)
        else:
            state = TaskState()

        try:
            result = work(state)
            # Success - optionally save final state
            if save_state_fn:
                save_state_fn(state)
            return result

        except SoftTimeLimitExceeded as e:
            # Timeout - checkpoint, cleanup, retry
            logger.warning(f"{log_prefix} Soft time limit exceeded, phase={state.phase}")
            if save_state_fn:
                save_state_fn(state)
            if cleanup_fn:
                self._safe_cleanup(cleanup_fn, state, log_prefix)
            raise self.retry(countdown=self.soft_retry_delay, exc=e)

        except TransientError as e:
            # Transient - checkpoint, cleanup, retry with backoff
            attempt = getattr(self.request, "retries", 0)
            delay = compute_backoff(
                attempt, base=self.transient_retry_base, cap=self.transient_retry_cap
            )
            logger.info(f"{log_prefix} TransientError, phase={state.phase}, retry in {delay}s: {e}")
            if save_state_fn:
                save_state_fn(state)
            if cleanup_fn:
                self._safe_cleanup(cleanup_fn, state, log_prefix)
            raise self.retry(countdown=delay, exc=e)

        except Retry:
            # Celery internal - re-raise
            raise

        except MissingResourceError as e:
            # Expected missing - mark MISSING_RESOURCE, no retry
            logger.warning(f"{log_prefix} MissingResourceError, phase={state.phase}: {e}")
            if mark_missing_fn:
                try:
                    mark_missing_fn(e)
                except Exception as mark_exc:
                    logger.warning(f"{log_prefix} Failed to mark missing: {mark_exc}")
            if cleanup_fn:
                self._safe_cleanup(cleanup_fn, state, log_prefix)
            raise

        except PermanentError as e:
            # Permanent - mark FAILED, no retry
            logger.error(f"{log_prefix} PermanentError, phase={state.phase}: {e}")
            if mark_failed_fn:
                try:
                    mark_failed_fn(e)
                except Exception as mark_exc:
                    logger.warning(f"{log_prefix} Failed to mark failed: {mark_exc}")
            if cleanup_fn:
                self._safe_cleanup(cleanup_fn, state, log_prefix)
            raise

        except Exception as e:
            # Unknown exception
            logger.exception(f"{log_prefix} Unexpected error, phase={state.phase}")
            if fail_on_unknown:
                # Treat as permanent
                if mark_failed_fn:
                    try:
                        mark_failed_fn(e)
                    except Exception as mark_exc:
                        logger.warning(f"{log_prefix} Failed to mark failed: {mark_exc}")
                if cleanup_fn:
                    self._safe_cleanup(cleanup_fn, state, log_prefix)
                raise
            else:
                # Treat as transient - retry
                attempt = getattr(self.request, "retries", 0)
                delay = compute_backoff(
                    attempt, base=self.transient_retry_base, cap=self.transient_retry_cap
                )
                if save_state_fn:
                    save_state_fn(state)
                if cleanup_fn:
                    self._safe_cleanup(cleanup_fn, state, log_prefix)
                raise self.retry(countdown=delay, exc=e)

    def _safe_cleanup(
        self, cleanup_fn: Callable[[TaskState], None], state: TaskState, log_prefix: str
    ) -> None:
        """Execute cleanup safely, catching any exceptions."""
        try:
            cleanup_fn(state)
        except Exception as cleanup_exc:
            logger.warning(f"{log_prefix} Cleanup failed: {cleanup_exc}")
