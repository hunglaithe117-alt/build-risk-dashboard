"""Periodic tasks responsible for keeping collectors running."""
from __future__ import annotations

from typing import Dict

from app.celery_app import celery_app
from app.services.queue_metrics import record_schedule_heartbeat
from app.tasks.base import PipelineTask
from app.tasks.workflow import poll_workflow_runs


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.scheduler.schedule_repository_scans")
def schedule_repository_scans(self: PipelineTask) -> Dict[str, int]:
    """Periodic job that enqueues workflow polling for every connected repository."""

    repositories = list(self.db.repositories.find())
    scheduled = 0
    for repo in repositories:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        branch = repo.get("default_branch")
        poll_workflow_runs.delay(full_name, branch, None, None)
        scheduled += 1

    record_schedule_heartbeat(self.db, scheduled)
    return {"scheduled_repositories": scheduled}

