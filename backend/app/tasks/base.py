import logging
from typing import Any

from celery import Task
from pymongo.database import Database

from app.database.mongo import get_database
from app.services.github.exceptions import (
    GithubRateLimitError,
    GithubRetryableError,
)


logger = logging.getLogger(__name__)


class PipelineTask(Task):
    abstract = True
    autoretry_for = (GithubRateLimitError, GithubRetryableError)
    retry_backoff = True
    retry_backoff_max = 100
    retry_kwargs = {"max_retries": 5}
    default_retry_delay = 20

    def __init__(self) -> None:
        self._db: Database | None = None

    # Celery wires the Task via class attributes; __call__ not invoked.
    def after_return(
        self, status: str, retval: Any, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover
        if self._db is not None:
            # PyMongo handles pooling; no need to close. Clear cache to avoid holding references.
            self._db = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_database()
        return self._db

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover - logging only
        logger.error("Task %s failed: %s", self.name, exc, exc_info=exc)
