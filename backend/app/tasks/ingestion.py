from app.ci_providers.models import BuildStatus
from app.entities.model_build import ExtractionStatus
from app.entities.model_repository import ImportStatus
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from bson import ObjectId
from pathlib import Path
import time
import asyncio

from app.celery_app import celery_app
from app.services.github.github_client import get_app_github_client
from app.tasks.base import PipelineTask
from app.services.github.exceptions import (
    GithubRateLimitError,
    GithubLogsUnavailableError,
)
from app.repositories.model_repository import ModelRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.entities.workflow_run import WorkflowRunRaw
from app.ci_providers import (
    CIProvider,
    get_provider_config,
    get_ci_provider,
)
from app.services.github.github_client import get_public_github_client

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
    test_frameworks: list[str] = [],
    source_languages: list[str] = [],
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    max_builds: int | None = None,
    since_days: int | None = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    import json
    from app.config import settings
    import redis

    model_repo_repo = ModelRepositoryRepository(self.db)
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

    since_dt = None
    if since_days:
        since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
        # Find existing repo to get ID (it should exist now)
        repo = model_repo_repo.find_one(
            {
                "user_id": ObjectId(user_id),
                "provider": "github",
                "full_name": full_name,
                "import_status": ImportStatus.QUEUED.value,
            }
        )
        if not repo:
            repo_doc = model_repo_repo.upsert_repository(
                user_id=user_id,
                full_name=full_name,
                data={
                    "provider": "github",
                    "default_branch": "main",
                    "is_private": False,
                    "main_lang": None,
                    "github_repo_id": None,
                    "metadata": {},
                    "installation_id": installation_id,
                    "last_scanned_at": None,
                    "test_frameworks": test_frameworks or [],
                    "source_languages": source_languages or [],
                    "ci_provider": ci_provider,
                    "import_status": ImportStatus.IMPORTING.value,
                    "max_builds_to_ingest": max_builds,
                    "since_days": since_days,
                    "only_with_logs": only_with_logs,
                },
            )
            repo_id = str(repo_doc.id)
        else:
            repo_id = str(repo.id)
            model_repo_repo.update_repository(
                repo_id, {"import_status": ImportStatus.IMPORTING.value}
            )

        publish_status(repo_id, "importing", "Fetching repository metadata...")

        # Determine which client to use
        if installation_id:
            client_context = get_app_github_client(self.db, installation_id)
        else:
            client_context = get_public_github_client()

        with client_context as gh:
            repo_data = gh.get_repository(full_name)

            model_repo_repo.update_repository(
                repo_id=repo_id,
                updates={
                    "default_branch": repo_data.get("default_branch", "main"),
                    "is_private": bool(repo_data.get("private")),
                    "main_lang": repo_data.get("language"),
                    "github_repo_id": repo_data.get("id"),
                    "metadata": repo_data,
                    "installation_id": installation_id,
                    "last_scanned_at": None,
                    "test_frameworks": test_frameworks or [],
                    "source_languages": source_languages,
                    "ci_provider": CIProvider(ci_provider),
                    "import_status": ImportStatus.IMPORTING.value,
                    "since_days": since_days,
                    "only_with_logs": only_with_logs,
                },
            )
            publish_status(repo_id, "importing", "Fetching builds from CI provider...")

            total_runs = 0
            latest_run_created_at = None
            runs_to_process = []

            # Get the latest synced run timestamp from the DB to avoid re-processing
            current_repo_doc = model_repo_repo.find_by_id(repo_id)
            last_synced_run_ts = None
            if current_repo_doc and current_repo_doc.latest_synced_run_created_at:
                last_synced_run_ts = current_repo_doc.latest_synced_run_created_at
                if last_synced_run_ts.tzinfo is None:
                    last_synced_run_ts = last_synced_run_ts.replace(tzinfo=timezone.utc)

            ci_provider_enum = CIProvider(ci_provider)
            provider_config = get_provider_config(ci_provider_enum)

            if ci_provider_enum == CIProvider.GITHUB_ACTIONS and installation_id:
                provider_config.token = gh._get_token()

            ci_provider_instance = get_ci_provider(
                ci_provider_enum, provider_config, db=self.db
            )

            builds = asyncio.get_event_loop().run_until_complete(
                ci_provider_instance.fetch_builds(
                    full_name,
                    since=since_dt,
                    limit=max_builds,
                    only_with_logs=(max_builds is None),
                    exclude_bots=True,
                )
            )

            logger.info(
                f"Fetched {len(builds)} builds from {ci_provider} for {full_name}"
            )

            for build in builds:
                run_id = build.build_id
                run_created_at = build.created_at

                # Only keep completed workflow runs
                if str(build.status).lower() != "completed":
                    continue

                # Filter by since_days
                if since_dt and run_created_at and run_created_at < since_dt:
                    continue

                # Create WorkflowRunRaw from BuildData
                # Normalize status/conclusion to enums (fallback to UNKNOWN)
                from app.entities.workflow_run import (
                    WorkflowRunStatus,
                    WorkflowConclusion,
                )

                try:
                    status_enum = WorkflowRunStatus(str(build.status))
                except Exception:
                    status_enum = WorkflowRunStatus.UNKNOWN

                try:
                    conclusion_enum = WorkflowConclusion(str(build.conclusion))
                except Exception:
                    conclusion_enum = WorkflowConclusion.UNKNOWN

                workflow_run = WorkflowRunRaw(
                    repo_id=ObjectId(repo_id),
                    workflow_run_id=int(run_id) if run_id.isdigit() else hash(run_id),
                    head_sha=build.commit_sha,
                    run_number=build.build_number,
                    status=status_enum,
                    conclusion=conclusion_enum,
                    ci_created_at=run_created_at or datetime.now(timezone.utc),
                    ci_updated_at=run_created_at or datetime.now(timezone.utc),
                    raw_payload=build.raw_data or {},
                    branch=build.branch,
                )

                existing = workflow_run_repo.find_by_repo_and_run_id(
                    repo_id, workflow_run.workflow_run_id
                )

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
                                "ci_updated_at": workflow_run.ci_updated_at,
                            },
                        )

                    if (
                        last_synced_run_ts
                        and workflow_run.ci_created_at <= last_synced_run_ts
                    ):
                        logger.info(
                            f"Reached previously synced run {run_id} ({workflow_run.ci_created_at}). Stopping backfill."
                        )
                        break
                else:
                    workflow_run_repo.insert_one(workflow_run)

                if run_created_at:
                    if (
                        latest_run_created_at is None
                        or run_created_at > latest_run_created_at
                    ):
                        latest_run_created_at = run_created_at

                runs_to_process.append(
                    (
                        run_created_at or datetime.now(timezone.utc),
                        workflow_run.workflow_run_id,
                    )
                )
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

            from app.repositories.model_build import ModelBuildRepository
            from app.entities.model_build import ModelBuild

            model_build_repo = ModelBuildRepository(self.db)
            for run_created_at, run_id in runs_to_process:
                existing = model_build_repo.find_by_repo_and_run_id(repo_id, run_id)
                if not existing:
                    workflow_run = workflow_run_repo.find_by_repo_and_run_id(
                        repo_id, run_id
                    )
                    if workflow_run:
                        build_status = (
                            workflow_run.conclusion or BuildStatus.UNKNOWN.value
                        )
                        model_build = ModelBuild(
                            repo_id=ObjectId(repo_id),
                            workflow_run_id=run_id,
                            head_sha=workflow_run.head_sha,
                            build_number=workflow_run.run_number,
                            build_created_at=workflow_run.ci_created_at,
                            status=build_status,
                            extraction_status=ExtractionStatus.PENDING.value,
                        )
                        model_build_repo.insert_one(model_build)

            logger.info(f"Scheduling {len(runs_to_process)} runs for processing")

            for _, run_id in runs_to_process:
                celery_app.send_task(
                    "app.tasks.processing.process_workflow_run",
                    args=[repo_id, run_id],
                )

            actual_build_count = model_build_repo.count_by_repo_id(repo_id)
            logger.info(
                f"Import complete for {full_name}: total_builds={actual_build_count}, latest_run={latest_run_created_at}"
            )

            model_repo_repo.update_repository(
                repo_id,
                {
                    "import_status": ImportStatus.IMPORTED.value,
                    "total_builds_imported": actual_build_count,
                    "last_scanned_at": datetime.now(timezone.utc),
                    "last_synced_at": datetime.now(timezone.utc),
                    "last_sync_status": "success",
                    "latest_synced_run_created_at": latest_run_created_at,
                },
            )
            publish_status(
                repo_id, "imported", f"Imported {actual_build_count} workflow runs."
            )

    except GithubRateLimitError as e:
        wait = e.retry_after if e.retry_after else 60
        logger.warning("Rate limit hit in import_repo. Retrying in %s seconds.", wait)
        raise self.retry(exc=e, countdown=wait)
    except Exception as e:
        logger.error(f"Failed to import repo {full_name}: {e}")
        if "repo_id" in locals():
            model_repo_repo.update_repository(
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
