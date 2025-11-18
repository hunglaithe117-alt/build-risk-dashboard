"""GitHub integration status helpers backed by MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from pymongo.database import Database

from app.services.pipeline_store_service import PipelineStore
from app.tasks.repositories import enqueue_repo_import


def list_import_jobs(db: Database) -> List[Dict[str, object]]:
    store = PipelineStore(db)
    return store.list_import_jobs()


def create_import_job(
    db: Database,
    repository: str,
    branch: str,
    initiated_by: str = "admin",
    user_id: str | None = None,
    installation_id: str | None = None,
) -> Dict[str, object]:
    store = PipelineStore(db)
    job = store.create_import_job(
        repository,
        branch,
        initiated_by,
        user_id=user_id,
        installation_id=installation_id,
    )
    job_id = job.get("id")
    start_time = datetime.now(timezone.utc)

    store.update_import_job(
        job_id,
        status="queued",
        progress=1,
        started_at=start_time,
        notes="Collecting repository metadata",
    )
    enqueue_repo_import.delay(repository, branch, job_id, user_id, installation_id)
    return store.update_import_job(
        job_id,
        status="waiting_webhook",
        notes="Metadata collected. Configure the GitHub webhook to receive workflow events.",
    )
