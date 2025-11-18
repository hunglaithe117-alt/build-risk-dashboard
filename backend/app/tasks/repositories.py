"""Celery tasks responsible for repository level ingestion."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from app.celery_app import celery_app
from app.config import settings
from app.services.pipeline_exceptions import PipelineConfigurationError
from app.tasks.base import PipelineTask


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.repositories.fetch_repo_snapshot")
def fetch_repo_snapshot(
    self: PipelineTask,
    repository: str,
    branch: Optional[str] = None,
    job_id: Optional[str] = None,
    user_id: Optional[int] = None,
    installation_id: Optional[str] = None,
) -> Dict[str, object]:
    """Fetch repository metadata and ensure language requirements are satisfied."""

    allowed_languages = {lang.lower() for lang in settings.PIPELINE_PRIMARY_LANGUAGES}
    now = datetime.now(timezone.utc)
    owner_id = user_id or settings.DEFAULT_REPO_OWNER_ID

    with self.github_client(installation_id) as gh:
        repo_data = gh.get_repository(repository)
        repo_language = (repo_data.get("language") or "").lower()

        if allowed_languages and repo_language and repo_language not in allowed_languages:
            raise PipelineConfigurationError(
                f"Repository {repository} is {repo_language} which is not in {allowed_languages}"
            )

    # Persist snapshot
    self.store.upsert_repository(
        user_id=owner_id,
        provider="github",
        full_name=repository,
        default_branch=repo_data.get("default_branch", "main"),
        is_private=bool(repo_data.get("private")),
        main_lang=repo_data.get("language"),
        github_repo_id=repo_data.get("id"),
        metadata=repo_data,
        installation_id=installation_id,
        last_scanned_at=now,
    )

    if job_id:
        self.store.update_import_job(
            job_id,
            status="waiting_webhook",
            started_at=now,
            progress=20,
            notes="Repository metadata collected. Configure the GitHub webhook to receive workflow runs.",
        )

    return {
        "repository": repository,
        "default_branch": repo_data.get("default_branch", "main"),
        "user_id": owner_id,
        "language": repo_data.get("language"),
    }


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.repositories.enqueue_repo_import")
def enqueue_repo_import(
    self: PipelineTask,
    repository: str,
    branch: str,
    job_id: Optional[str],
    user_id: Optional[int],
    installation_id: Optional[str],
) -> Dict[str, object]:
    """Entry-point task triggered by the API to ingest a repository."""

    owner_id = user_id or settings.DEFAULT_REPO_OWNER_ID
    fetch_repo_snapshot.delay(repository, branch, job_id, owner_id, installation_id)
    return {
        "repository": repository,
        "branch": branch,
        "job_id": job_id,
        "user_id": owner_id,
        "installation_id": installation_id,
    }
