"""
Base Celery Task with automatic TracingContext propagation.

All PipelineTask subclasses automatically:
1. Restore TracingContext from `correlation_id` kwarg (if present)
2. Set task_name from the Celery task name
3. Clear TracingContext on task completion
"""

import logging
from typing import Any

from celery import Task
from pymongo.database import Database

from app.core.tracing import TracingContext
from app.database.mongo import get_database
from app.services.github.exceptions import (
    GithubRateLimitError,
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
    """

    abstract = True
    autoretry_for = (GithubRateLimitError, GithubRetryableError)
    retry_backoff = True
    retry_backoff_max = 100
    retry_kwargs = {"max_retries": 5}
    default_retry_delay = 20

    def __init__(self) -> None:
        self._db: Database | None = None

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
        logger.error("Task %s failed: %s", self.name, exc, exc_info=exc)
