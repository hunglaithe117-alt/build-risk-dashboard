"""Periodic tasks responsible for keeping collectors running."""
from __future__ import annotations

from typing import Dict

from app.celery_app import celery_app
from app.services.queue_metrics import record_schedule_heartbeat
from app.tasks.base import PipelineTask


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.scheduler.schedule_repository_scans")
def schedule_repository_scans(self: PipelineTask) -> Dict[str, int]:
    """Periodic job that records how many repositories are eligible for scanning."""

    repositories = list(self.db.repositories.find())
    scheduled = len(repositories)

    record_schedule_heartbeat(self.db, scheduled)
    return {"scheduled_repositories": scheduled}
