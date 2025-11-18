"""Common Celery task utilities."""

from __future__ import annotations

import logging
from typing import Any, Optional

from celery import Task
from pymongo.database import Database

from app.database.mongo import get_database

from app.services.github_client import GitHubClient, get_pipeline_github_client
from app.services.pipeline_exceptions import (
    PipelineRateLimitError,
    PipelineRetryableError,
)
from app.services.pipeline_store_service import PipelineStore


logger = logging.getLogger(__name__)


class PipelineTask(Task):
    """Base Celery task with Mongo + GitHub helpers."""

    abstract = True
    autoretry_for = (PipelineRateLimitError, PipelineRetryableError)
    retry_backoff = True
    retry_backoff_max = 600
    retry_kwargs = {"max_retries": 5}
    default_retry_delay = 30

    def __init__(self) -> None:
        self._db: Database | None = None
        self._store: PipelineStore | None = None

    # Celery wires the Task via class attributes; __call__ not invoked.
    def after_return(
        self, status: str, retval: Any, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover
        if self._db is not None:
            # PyMongo handles pooling; no need to close. Clear cache to avoid holding references.
            self._db = None
            self._store = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_database()
        return self._db

    @property
    def store(self) -> PipelineStore:
        if self._store is None:
            self._store = PipelineStore(self.db)
        return self._store

    def github_client(self, installation_id: Optional[str] = None) -> GitHubClient:
        return get_pipeline_github_client(self.db, installation_id)

    def github_client_for_repository(self, repository: str) -> GitHubClient:
        repo_doc = self.db.repositories.find_one({"full_name": repository}) or {}
        installation_id = repo_doc.get("installation_id") or repo_doc.get(
            "installationId"
        )
        if installation_id is not None:
            return self.github_client(str(installation_id))
        return self.github_client()

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo
    ):  # pragma: no cover - logging only
        logger.error("Task %s failed: %s", self.name, exc, exc_info=exc)
