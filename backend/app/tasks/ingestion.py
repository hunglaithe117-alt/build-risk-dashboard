"""Ingestion tasks for repository backfill"""

from app.models.entities.imported_repository import ImportStatus
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from bson import ObjectId
import os
from pathlib import Path

from app.celery_app import celery_app
from app.services.github.github_client import get_app_github_client
from app.tasks.base import PipelineTask
from app.services.github.exceptions import GithubRateLimitError
from app.repositories.imported_repository import ImportedRepositoryRepository


logger = logging.getLogger(__name__)

LOG_DIR = Path("job_logs")
LOG_DIR.mkdir(exist_ok=True)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.ingestion.import_repo",
    queue="import_repo",
)
def import_repo(
    self: PipelineTask,
    user_id: str,
    full_name: str,
    installation_id: str,
    provider: str = "github",
    test_frameworks: list[str] | None = None,
    source_languages: list[str] | None = None,
    ci_provider: str = "github_actions",
) -> Dict[str, Any]:
    import json
    from app.config import settings
    import redis

    imported_repo_repo = ImportedRepositoryRepository(self.db)
    redis_client = redis.from_url(settings.REDIS_URL)

    def publish_status(repo_id: str, status: str, message: str = ""):
        try:
            redis_client.publish(
                "events",
                json.dumps(
                    {
                        "type": "REPO_UPDATE",
                        "payload": {
                            "repo_id": repo_id,
                            "status": status,
                            "message": message,
                        },
                    }
                ),
            )
        except Exception as e:
            logger.error(f"Failed to publish status update: {e}")

    # 1. Fetch metadata
    try:
        # Find existing repo to get ID (it should exist now)
        repo = imported_repo_repo.find_one(
            {
                "provider": provider,
                "full_name": full_name,
                "import_status": ImportStatus.QUEUED.value,
            }
        )
        if not repo:
            # Fallback if not found (shouldn't happen with new flow)
            repo_doc = imported_repo_repo.upsert_repository(
                query={"provider": provider, "full_name": full_name},
                data={
                    "user_id": user_id,
                    "default_branch": "main",
                    "is_private": False,
                    "main_lang": None,
                    "github_repo_id": None,
                    "metadata": {},
                    "installation_id": installation_id,
                    "last_scanned_at": None,
                    "test_frameworks": test_frameworks or [],
                    "source_languages": source_languages or [],
                    "ci_provider": ci_provider or "github_actions",
                    "import_status": ImportStatus.IMPORTING.value,
                },
            )
            repo_id = str(repo_doc.id)
        else:
            repo_id = str(repo.id)
            imported_repo_repo.update_repository(
                repo_id, {"import_status": ImportStatus.IMPORTING.value}
            )

        publish_status(repo_id, "importing", "Fetching repository metadata...")

        with get_app_github_client(self.db, installation_id) as gh:
            repo_data = gh.get_repository(full_name)

            imported_repo_repo.upsert_repository(
                query={"provider": provider, "full_name": full_name},
                data={
                    "user_id": user_id,
                    "default_branch": repo_data.get("default_branch", "main"),
                    "is_private": bool(repo_data.get("private")),
                    "main_lang": repo_data.get("language"),
                    "github_repo_id": repo_data.get("id"),
                    "metadata": repo_data,
                    "installation_id": installation_id,
                    "last_scanned_at": None,
                    "test_frameworks": test_frameworks or [],
                    "source_languages": source_languages or [],
                    "ci_provider": ci_provider or "github_actions",
                    "import_status": ImportStatus.IMPORTING.value,
                },
            )

            self.db.available_repositories.update_one(
                {"user_id": ObjectId(user_id), "full_name": full_name},
                {"$set": {"imported": True}},
            )

            publish_status(repo_id, "importing", "Fetching workflow runs...")

            total_runs = 0
            for run in gh.paginate_workflow_runs(
                full_name, params={"per_page": 100, "status": "completed"}
            ):
                run_id = run.get("id")
                if not gh.logs_available(full_name, run_id):
                    logger.info(
                        f"Logs expired for run {run_id} in {full_name}. Stopping backfill."
                    )
                    break

                process_workflow_run.delay(repo_id, run)
                total_runs += 1

            imported_repo_repo.update_repository(
                repo_id,
                {
                    "import_status": "imported",
                    "total_builds_imported": total_runs,
                    "last_scanned_at": datetime.now(timezone.utc),
                },
            )
            publish_status(repo_id, "imported", f"Imported {total_runs} workflow runs.")

    except GithubRateLimitError as e:
        wait = e.retry_after if e.retry_after else 60
        logger.warning("Rate limit hit in import_repo. Retrying in %s seconds.", wait)
        raise self.retry(exc=e, countdown=wait)
    except Exception as e:
        logger.error(f"Failed to import repo {full_name}: {e}")
        if "repo_id" in locals():
            imported_repo_repo.update_repository(
                repo_id, {"import_status": "failed", "last_sync_error": str(e)}
            )
            publish_status(repo_id, "failed", str(e))
        raise e

    return {
        "status": "completed",
        "repo_id": repo_id if "repo_id" in locals() else None,
        "runs_found": len(runs) if "runs" in locals() else 0,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.ingestion.process_workflow_run",
    queue="collect_workflow_logs",
)
def process_workflow_run(
    self: PipelineTask, repo_id: str, run: Dict[str, Any]
) -> Dict[str, Any]:
    repo_repo = ImportedRepositoryRepository(self.db)
    repo = repo_repo.find_by_id(repo_id)
    if not repo:
        return {"status": "error", "message": "Repository not found"}

    full_name = repo.full_name
    installation_id = repo.installation_id
    run_id = run.get("id")

    if not installation_id:
        raise ValueError(f"Repository {full_name} missing installation_id")

    try:
        with get_app_github_client(self.db, installation_id) as gh:
            jobs = gh.list_workflow_jobs(full_name, run_id)

            logs_collected = 0
            for job in jobs:
                job_id = job.get("id")
                try:
                    log_content = gh.download_job_logs(full_name, job_id)
                    if log_content:
                        logs_collected += 1
                        # Save log to file
                        log_path = LOG_DIR / str(repo_id) / str(run_id)
                        log_path.mkdir(parents=True, exist_ok=True)
                        file_path = log_path / f"{job_id}.log"
                        with open(file_path, "wb") as f:
                            f.write(log_content)
                except Exception as e:
                    logger.error(
                        "Failed to download logs for job %s in run %s (repo: %s): %s",
                        job_id,
                        run_id,
                        full_name,
                        str(e),
                        exc_info=True,
                    )
    except GithubRateLimitError as e:
        wait = e.retry_after if e.retry_after else 60
        logger.warning(
            "Rate limit hit in process_workflow_run. Retrying in %s seconds.", wait
        )
        raise self.retry(exc=e, countdown=wait)

    return {
        "repo_id": repo_id,
        "run_id": run_id,
        "jobs_processed": len(jobs),
        "logs_collected": logs_collected,
    }
