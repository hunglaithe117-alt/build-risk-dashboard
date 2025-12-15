"""
Model Ingestion Tasks - Chain-based workflow for importing repositories.

This module implements a clean, chain-based Celery workflow:
1. import_repo - Orchestrator that starts the chain
2. clone_repo (from shared) - Clone/update the git repository
3. fetch_and_save_builds - Fetch builds from CI provider and save to DB
4. download_build_logs (from shared) - Download build logs
5. create_worktrees (from shared) - Create git worktrees
6. dispatch_processing - Schedule feature extraction in batches
"""

from app.repositories.raw_repository import RawRepositoryRepository
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId
from celery import chain, group
import redis
import json

from app.celery_app import celery_app
from app.config import settings
from app.tasks.base import PipelineTask
from app.entities.enums import ExtractionStatus, ModelImportStatus
from app.entities.raw_build_run import RawBuildRun
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.ci_providers import CIProvider, get_provider_config, get_ci_provider
from app.ci_providers.models import BuildStatus, BuildConclusion
from app.services.github.exceptions import GithubRateLimitError
from app.paths import REPOS_DIR
from app.tasks.pipeline.feature_dag._metadata import (
    get_required_resources_for_features,
    FeatureResource,
)
from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
from app.repositories.dataset_template_repository import DatasetTemplateRepository

# Import shared ingestion tasks and helpers
from app.tasks.shared import build_ingestion_workflow

logger = logging.getLogger(__name__)


def get_redis_client():
    """Get Redis client for publishing events."""
    return redis.from_url(settings.REDIS_URL)


def publish_status(repo_id: str, status: str, message: str = ""):
    """Publish status update to Redis for real-time UI updates."""
    try:
        redis_client = get_redis_client()
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


def get_required_resources_for_template(
    db, template_name: str = "TravisTorrent Full"
) -> set:
    template_repo = DatasetTemplateRepository(db)
    template = template_repo.find_by_name(template_name)
    if template and template.feature_names:
        feature_set = set(template.feature_names)
        return get_required_resources_for_features(feature_set)
    return {r.value for r in FeatureResource}


# Task 1: import_repo - Orchestrator
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.import_repo",
    queue="import_repo",
)
def import_repo(
    self: PipelineTask,
    user_id: str,
    full_name: str,
    installation_id: str,
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator task - kicks off the import chain.

    Chain: clone_repo -> fetch_and_save_builds -> dispatch_processing
    """
    model_repo_repo = ModelRepoConfigRepository(self.db)

    try:
        # Find existing repo config
        repo = model_repo_repo.find_one(
            {
                "user_id": ObjectId(user_id),
                "provider": "github",
                "full_name": full_name,
            }
        )

        if not repo:
            raise ValueError(
                "ModelRepoConfig not found. Create it via RepositoryService first."
            )

        repo_id = str(repo.id)
        model_repo_repo.update_repository(
            repo_id,
            {
                "import_status": ModelImportStatus.IMPORTING.value,
                "installation_id": installation_id,
                "ci_provider": ci_provider,
            },
        )

        publish_status(repo_id, "importing", "Starting import workflow...")

        # Determine required resources based on template
        required_resources = get_required_resources_for_template(self.db)

        # Get tasks grouped by level from resource_dag
        tasks_by_level = get_ingestion_tasks_by_level(list(required_resources))

        logger.info(
            f"Required resources for {full_name}: {required_resources}. "
            f"Tasks by level: {tasks_by_level}"
        )

        # Add fetch_and_save_builds to level 0 (always needed for model pipeline)
        if 0 not in tasks_by_level:
            tasks_by_level[0] = []
        if "fetch_and_save_builds" not in tasks_by_level.get(0, []):
            tasks_by_level[0].append("fetch_and_save_builds")

        # Build workflow
        workflow = build_ingestion_workflow(
            tasks_by_level=tasks_by_level,
            repo_id=repo_id,
            full_name=full_name,
            ci_provider=ci_provider,
            installation_id=installation_id,
            publish_status=True,
            enable_fork_replay=True,
            final_task=dispatch_processing.s(repo_id=repo_id),
            custom_tasks={
                "fetch_and_save_builds": fetch_and_save_builds.s(
                    repo_id=repo_id,
                    full_name=full_name,
                    installation_id=installation_id,
                    ci_provider=ci_provider,
                    max_builds=max_builds,
                    since_days=since_days,
                    only_with_logs=only_with_logs,
                ),
            },
        )

        if workflow:
            workflow.apply_async()

        return {
            "status": "queued",
            "repo_id": repo_id,
            "message": "Import workflow started",
        }

    except Exception as e:
        logger.error(f"Failed to start import for {full_name}: {e}")
        if "repo_id" in locals():
            model_repo_repo.update_repository(
                repo_id,
                {
                    "import_status": ModelImportStatus.FAILED.value,
                    "last_sync_error": str(e),
                },
            )
            publish_status(repo_id, "failed", str(e))
        raise


# Task 2: fetch_and_save_builds - Fetch from CI and save to DB
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.fetch_and_save_builds",
    queue="import_repo",
    autoretry_for=(GithubRateLimitError,),
    retry_kwargs={"max_retries": 5},
)
def fetch_and_save_builds(
    self: PipelineTask,
    clone_result: Dict[str, Any],  # Result from clone_repo
    repo_id: str,
    full_name: str,
    installation_id: str,
    ci_provider: str,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Fetch builds from CI provider and save to database in batches.
    """
    publish_status(repo_id, "importing", "Fetching builds from CI provider...")

    model_repo_repo = ModelRepoConfigRepository(self.db)
    build_run_repo = RawBuildRunRepository(self.db)
    model_build_repo = ModelTrainingBuildRepository(self.db)

    since_dt = None
    if since_days:
        since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)

    batch_size = settings.PROCESSING_BATCH_SIZE

    try:
        # Get CI provider instance
        ci_provider_enum = CIProvider(ci_provider)
        provider_config = get_provider_config(ci_provider_enum)
        ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

        # Fetch builds with internal pagination (CI provider handles per_page)
        fetch_kwargs = {
            "since": since_dt,
            "limit": max_builds,
            "exclude_bots": True,
            "only_with_logs": only_with_logs,
        }
        if ci_provider_enum == CIProvider.GITHUB_ACTIONS and installation_id:
            fetch_kwargs["installation_id"] = installation_id

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            builds = loop.run_until_complete(
                ci_instance.fetch_builds(full_name, **fetch_kwargs)
            )
        finally:
            loop.close()

        total_fetched = len(builds)
        logger.info(
            f"Fetched {total_fetched} builds from {ci_provider} for {full_name}"
        )
        publish_status(
            repo_id, "importing", f"Found {total_fetched} builds, saving in batches..."
        )

        # Process and save builds in batches
        saved_count = 0
        build_ids = []

        for batch_start in range(0, len(builds), batch_size):
            batch_end = min(batch_start + batch_size, len(builds))
            batch = builds[batch_start:batch_end]
            batch_saved = 0

            for build in batch:
                if build.status != BuildStatus.COMPLETED:
                    continue

                run_id = build.build_id

                # Check if already exists
                build_run = build_run_repo.find_by_repo_and_build_id(repo_id, run_id)

                if not build_run:
                    build_run = RawBuildRun(
                        _id=None,
                        raw_repo_id=ObjectId(repo_id),
                        build_id=run_id,
                        build_number=build.build_number,
                        repo_name=full_name,
                        branch=build.branch or "",
                        commit_sha=build.commit_sha,
                        commit_message=None,
                        commit_author=None,
                        status=build.status,
                        conclusion=build.conclusion,
                        created_at=build.created_at or datetime.now(timezone.utc),
                        started_at=None,
                        completed_at=build.created_at or datetime.now(timezone.utc),
                        duration_seconds=build.duration_seconds,
                        web_url=build.web_url,
                        logs_url=None,
                        logs_available=False,
                        logs_path=None,
                        provider=ci_provider_enum,
                        raw_data=build.raw_data or {},
                        is_bot_commit=False,
                    )
                    build_run = build_run_repo.insert_one(build_run)
                    batch_saved += 1

                # Check if ModelTrainingBuild already exists
                existing_model_build = model_build_repo.find_by_workflow_run(
                    ObjectId(repo_id), build_run.id
                )

                if not existing_model_build:
                    model_build = ModelTrainingBuild(
                        _id=None,
                        raw_repo_id=ObjectId(repo_id),
                        raw_workflow_run_id=build_run.id,
                        model_repo_config_id=ObjectId(repo_id),
                        head_sha=build.commit_sha,
                        build_number=build.build_number,
                        build_created_at=build.created_at,
                        build_conclusion=build.conclusion or BuildConclusion.UNKNOWN,
                        extraction_status=ExtractionStatus.PENDING,
                    )
                    model_build_repo.insert_one(model_build)

                build_ids.append(build_run.build_id)

            saved_count += batch_saved

            # Progress update after each batch
            publish_status(
                repo_id,
                "importing",
                f"Saved builds: {batch_end}/{total_fetched} ({saved_count} new)",
            )

        # Update repo with build count
        model_repo_repo.update_repository(
            repo_id,
            {
                "total_builds_imported": model_build_repo.count_by_repo_id(repo_id),
                "last_synced_at": datetime.now(timezone.utc),
            },
        )

        publish_status(repo_id, "importing", f"Saved {saved_count} new builds")

        return {
            "repo_id": repo_id,
            "builds_saved": saved_count,
            "total_builds": len(build_ids),
            "build_ids": build_ids,
        }

    except GithubRateLimitError as e:
        wait = e.retry_after if e.retry_after else 60
        logger.warning(f"Rate limit hit. Retrying in {wait}s")
        raise self.retry(countdown=wait)
    except Exception as e:
        logger.error(f"Failed to fetch builds for {full_name}: {e}")
        raise


# Task 3: dispatch_processing - Schedule feature extraction in batches
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.dispatch_processing",
    queue="import_repo",
)
def dispatch_processing(
    self: PipelineTask,
    fetch_result: Dict[str, Any],  # Result from previous task
    repo_id: str,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Dispatch feature extraction tasks in batches.
    """
    import time

    # Use config default if not specified
    if batch_size is None:
        batch_size = settings.PROCESSING_BATCH_SIZE

    build_ids = fetch_result.get("build_ids", [])

    if not build_ids:
        logger.info(f"No builds to process for repo {repo_id}")

        model_repo_repo = ModelRepoConfigRepository(self.db)
        model_repo_repo.update_repository(
            repo_id,
            {
                "import_status": ModelImportStatus.IMPORTED.value,
            },
        )
        publish_status(repo_id, "imported", "No new builds to process")

        return {"repo_id": repo_id, "dispatched": 0}

    publish_status(
        repo_id, "importing", f"Scheduling {len(build_ids)} builds for processing..."
    )

    dispatched = 0

    # Process in batches
    for i in range(0, len(build_ids), batch_size):
        batch = build_ids[i : i + batch_size]

        # Create a group of tasks for this batch
        tasks = group(
            [
                celery_app.signature(
                    "app.tasks.processing.process_workflow_run",
                    args=[repo_id, build_id],
                )
                for build_id in batch
            ]
        )
        tasks.apply_async()

        dispatched += len(batch)
        logger.info(f"Dispatched batch {i // batch_size + 1}: {len(batch)} tasks")

        # Delay between batches to prevent queue flooding
        # This gives workers time to pick up tasks before more are added
        if i + batch_size < len(build_ids):
            time.sleep(1.0)

    # Mark import as complete
    model_repo_repo = ModelRepoConfigRepository(self.db)
    model_repo_repo.update_repository(
        repo_id,
        {
            "import_status": ModelImportStatus.IMPORTED.value,
            "last_sync_status": "success",
        },
    )

    publish_status(
        repo_id, "imported", f"Dispatched {dispatched} builds for processing"
    )

    return {
        "repo_id": repo_id,
        "dispatched": dispatched,
        "status": "completed",
    }
