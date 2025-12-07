from app.entities.imported_repository import ImportStatus
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from bson import ObjectId
from pathlib import Path
import time

from app.celery_app import celery_app
from app.services.github.github_client import get_app_github_client
from app.tasks.base import PipelineTask
from app.services.github.exceptions import GithubRateLimitError
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.entities.workflow_run import WorkflowRunRaw


logger = logging.getLogger(__name__)

LOG_DIR = Path("../repo-data/job_logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


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
    feature_ids: list[str] | None = None,
    max_builds: int | None = None,
    ingest_start_date: str | None = None,
    ingest_end_date: str | None = None,
) -> Dict[str, Any]:
    import json
    from app.config import settings
    import redis

    imported_repo_repo = ImportedRepositoryRepository(self.db)
    workflow_run_repo = WorkflowRunRepository(self.db)
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
    from datetime import datetime

    def _parse_date(val: str | None):
        if not val:
            return None
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None

    start_dt = _parse_date(ingest_start_date)
    end_dt = _parse_date(ingest_end_date)

    try:
        # Find existing repo to get ID (it should exist now)
        repo = imported_repo_repo.find_one(
            {
                "user_id": ObjectId(user_id),
                "provider": provider,
                "full_name": full_name,
                "import_status": ImportStatus.QUEUED.value,
            }
        )
        if not repo:
            repo_doc = imported_repo_repo.upsert_repository(
                query={
                    "user_id": ObjectId(user_id),
                    "provider": provider,
                    "full_name": full_name,
                },
                data={
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
                    "requested_feature_ids": [
                        ObjectId(fid) for fid in (feature_ids or [])
                    ],
                    "max_builds_to_ingest": max_builds,
                    "ingest_start_date": start_dt,
                    "ingest_end_date": end_dt,
                },
            )
            repo_id = str(repo_doc.id)
        else:
            repo_id = str(repo.id)
            imported_repo_repo.update_repository(
                repo_id, {"import_status": ImportStatus.IMPORTING.value}
            )

        publish_status(repo_id, "importing", "Fetching repository metadata...")

        # Determine which client to use
        if installation_id:
            client_context = get_app_github_client(self.db, installation_id)
        else:
            # Public repo import using system tokens
            from app.services.github.github_client import get_public_github_client

            client_context = get_public_github_client()

        with client_context as gh:
            repo_data = gh.get_repository(full_name)

            detected_languages = []
            try:
                lang_stats = gh.list_languages(full_name) or {}
                detected_languages = [
                    lang.lower()
                    for lang, _ in sorted(
                        lang_stats.items(), key=lambda kv: kv[1], reverse=True
                    )[:5]
                ]
            except Exception as e:
                logger.warning(f"Failed to detect languages for {full_name}: {e}")

            if not detected_languages:
                detected_languages = source_languages or ["ruby", "java", "python"]

            imported_repo_repo.update_repository(
                repo_id=repo_id,
                updates={
                    "default_branch": repo_data.get("default_branch", "main"),
                    "is_private": bool(repo_data.get("private")),
                    "main_lang": (
                        detected_languages[0]
                        if detected_languages
                        else repo_data.get("language")
                    ),
                    "github_repo_id": repo_data.get("id"),
                    "metadata": repo_data,
                    "installation_id": installation_id,
                    "last_scanned_at": None,
                    "test_frameworks": test_frameworks or [],
                    "source_languages": source_languages or detected_languages,
                    "ci_provider": ci_provider or "github_actions",
                    "import_status": ImportStatus.IMPORTING.value,
                    "ingest_end_date": end_dt,
                    "requested_feature_ids": [
                        ObjectId(fid) for fid in (feature_ids or [])
                    ],
                },
            )
            publish_status(repo_id, "importing", "Fetching workflow runs...")

            total_runs = 0
            latest_run_created_at = None
            runs_to_process = []

            # Get the latest synced run timestamp from the DB to avoid re-processing
            current_repo_doc = imported_repo_repo.find_by_id(repo_id)
            last_synced_run_ts = None
            if current_repo_doc and current_repo_doc.latest_synced_run_created_at:
                last_synced_run_ts = current_repo_doc.latest_synced_run_created_at
                # Ensure timezone awareness
                if last_synced_run_ts.tzinfo is None:
                    last_synced_run_ts = last_synced_run_ts.replace(tzinfo=timezone.utc)

            # Metadata Collection (Newest -> Oldest)
            for run in gh.paginate_workflow_runs(full_name, params={"per_page": 100}):
                run_id = run.get("id")
                created_at_str = run.get("created_at")
                if created_at_str:
                    run_created_at = datetime.fromisoformat(
                        created_at_str.replace("Z", "+00:00")
                    )
                    if start_dt and run_created_at < start_dt:
                        continue
                    if end_dt and run_created_at > end_dt:
                        continue

                # Filter out bot-triggered workflow runs (e.g., Dependabot, github-actions[bot])
                triggering_actor = run.get("triggering_actor", {})
                actor_type = triggering_actor.get("type")
                if actor_type == "Bot":
                    logger.info(
                        f"Skipping bot-triggered run {run_id} in {full_name} (triggered by {triggering_actor.get('login', 'unknown bot')})"
                    )
                    continue

                workflow_run = WorkflowRunRaw(
                    repo_id=ObjectId(repo_id),
                    workflow_run_id=run_id,
                    head_sha=run.get("head_sha"),
                    run_number=run.get("run_number"),
                    status=run.get("status"),
                    conclusion=run.get("conclusion"),
                    created_at=datetime.fromisoformat(
                        run.get("created_at").replace("Z", "+00:00")
                    ),
                    updated_at=datetime.fromisoformat(
                        run.get("updated_at").replace("Z", "+00:00")
                    ),
                    raw_payload=run,
                    log_fetched=False,
                )

                existing = workflow_run_repo.find_by_repo_and_run_id(repo_id, run_id)

                if existing:
                    if (
                        existing.status != workflow_run.status
                        or existing.conclusion != workflow_run.conclusion
                    ):
                        workflow_run_repo.update_one(
                            str(existing.id),
                            {
                                "status": workflow_run.status,
                                "conclusion": workflow_run.conclusion,
                                "updated_at": workflow_run.updated_at,
                            },
                        )

                    if (
                        last_synced_run_ts
                        and workflow_run.created_at <= last_synced_run_ts
                    ):
                        logger.info(
                            f"Reached previously synced run {run_id} ({workflow_run.created_at}). Stopping backfill."
                        )
                        break
                else:
                    workflow_run_repo.insert_one(workflow_run)

                run_created_at = workflow_run.created_at
                if (
                    latest_run_created_at is None
                    or run_created_at > latest_run_created_at
                ):
                    latest_run_created_at = run_created_at

                runs_to_process.append((run_created_at, run_id))
                total_runs += 1

                if max_builds and total_runs >= max_builds:
                    logger.info(
                        "Reached requested max_builds (%s) for %s",
                        max_builds,
                        full_name,
                    )
                    break

            # Processing (Oldest -> Newest)
            runs_to_process.sort(key=lambda x: x[0])

            publish_status(
                repo_id,
                "importing",
                f"Scheduling {len(runs_to_process)} runs for processing...",
            )

            for _, run_id in runs_to_process:
                download_job_logs.delay(repo_id, run_id)

            imported_repo_repo.update_repository(
                repo_id,
                {
                    "import_status": ImportStatus.IMPORTED.value,
                    "total_builds_imported": total_runs,
                    "last_scanned_at": datetime.now(timezone.utc),
                    "last_synced_at": datetime.now(timezone.utc),
                    "last_sync_status": "success",
                    "latest_synced_run_created_at": latest_run_created_at,
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
                repo_id,
                {
                    "import_status": ImportStatus.FAILED.value,
                    "last_sync_error": str(e),
                    "last_sync_status": "failed",
                    "last_synced_at": datetime.now(timezone.utc),
                },
            )
            publish_status(repo_id, "failed", str(e))
        raise e

    return {
        "status": "completed",
        "repo_id": repo_id if "repo_id" in locals() else None,
        "runs_found": total_runs,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.ingestion.download_job_logs",
    queue="collect_workflow_logs",
)
def download_job_logs(self: PipelineTask, repo_id: str, run_id: int) -> Dict[str, Any]:
    repo_repo = ImportedRepositoryRepository(self.db)
    repo = repo_repo.find_by_id(repo_id)
    if not repo:
        return {"status": "error", "message": "Repository not found"}

    full_name = repo.full_name
    installation_id = repo.installation_id

    if installation_id:
        client_context = get_app_github_client(self.db, installation_id)
    else:
        from app.services.github.github_client import get_public_github_client

        client_context = get_public_github_client()

    jobs = []
    logs_collected = 0
    try:
        with client_context as gh:
            jobs = gh.list_workflow_jobs(full_name, run_id)

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

                        time.sleep(0.1)

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
            "Rate limit hit in download_job_logs. Retrying in %s seconds.", wait
        )
        raise self.retry(exc=e, countdown=wait)

    # Update WorkflowRunRaw.log_fetched = true
    workflow_run_repo = WorkflowRunRepository(self.db)
    workflow_run = workflow_run_repo.find_by_repo_and_run_id(repo_id, run_id)
    if workflow_run:
        workflow_run_repo.update_one(str(workflow_run.id), {"log_fetched": True})

    # Trigger orchestrator
    celery_app.send_task(
        "app.tasks.processing.process_workflow_run", args=[repo_id, run_id]
    )

    return {
        "repo_id": repo_id,
        "run_id": run_id,
        "jobs_processed": len(jobs),
        "logs_collected": logs_collected,
    }
