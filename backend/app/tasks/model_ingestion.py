"""
Model Ingestion Tasks - Chain-based workflow for importing repositories.

This module implements a clean, chain-based Celery workflow:
1. import_repo - Orchestrator that starts the chain
2. clone_repo - Clone/update the git repository
3. fetch_and_save_builds - Fetch builds from CI provider and save to DB
4. dispatch_processing - Schedule feature extraction in batches
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from bson import ObjectId
from celery import chain, group
import redis
import json
import subprocess

from app.celery_app import celery_app
from app.config import settings
from app.tasks.base import PipelineTask
from app.entities.enums import ExtractionStatus, ModelImportStatus
from backend.app.entities.raw_build_run import RawWorkflowRun
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.model_repo_config import ModelRepoConfigRepository
from backend.app.repositories.raw_build_run import RawWorkflowRunRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.ci_providers import CIProvider, get_provider_config, get_ci_provider
from app.ci_providers.models import BuildStatus, BuildConclusion
from app.services.github.exceptions import GithubRateLimitError

logger = logging.getLogger(__name__)

# Directories
REPOS_DIR = (
    Path(settings.REPO_MIRROR_ROOT) / "repos"
    if hasattr(settings, "REPO_MIRROR_ROOT")
    else Path("../repo-data/repos")
)
REPOS_DIR.mkdir(parents=True, exist_ok=True)


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

        # Always run: clone -> fetch -> dispatch
        workflow = chain(
            clone_repo.s(repo_id, full_name, installation_id),
            fetch_and_save_builds.s(
                repo_id=repo_id,
                full_name=full_name,
                installation_id=installation_id,
                ci_provider=ci_provider,
                max_builds=max_builds,
                since_days=since_days,
                only_with_logs=only_with_logs,
            ),
            dispatch_processing.s(repo_id=repo_id),
        )
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


# Task 2: clone_repo - Clone/update git repository
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.clone_repo",
    queue="import_repo",
    autoretry_for=(subprocess.CalledProcessError,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
)
def clone_repo(
    self: PipelineTask,
    repo_id: str,
    full_name: str,
    installation_id: str,
) -> Dict[str, Any]:
    """
    Clone or update the git repository.

    Returns repo_id for chaining.
    """
    publish_status(repo_id, "importing", "Cloning repository...")

    repo_path = REPOS_DIR / repo_id

    try:
        if repo_path.exists():
            # Update existing clone
            logger.info(f"Updating existing clone for {full_name}")
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=300,
            )
        else:
            # Clone new repo
            logger.info(f"Cloning {full_name} to {repo_path}")
            clone_url = f"https://github.com/{full_name}.git"

            # For private repos, we need to use the installation token
            if installation_id:
                from app.services.github.github_app import get_installation_token

                token = get_installation_token(installation_id, self.db)
                clone_url = f"https://x-access-token:{token}@github.com/{full_name}.git"

            subprocess.run(
                ["git", "clone", "--bare", clone_url, str(repo_path)],
                check=True,
                capture_output=True,
                timeout=600,
            )

        publish_status(repo_id, "importing", "Repository cloned successfully")
        return {"repo_id": repo_id, "status": "cloned"}

    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed for {full_name}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Failed to clone {full_name}: {e}")
        raise


# Task 3: fetch_and_save_builds - Fetch from CI and save to DB


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
    Fetch builds from CI provider and save to database.

    Returns list of build IDs for processing.
    """
    publish_status(repo_id, "importing", "Fetching builds from CI provider...")

    model_repo_repo = ModelRepoConfigRepository(self.db)
    workflow_run_repo = RawWorkflowRunRepository(self.db)
    model_build_repo = ModelTrainingBuildRepository(self.db)

    since_dt = None
    if since_days:
        since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
        # Get CI provider instance
        ci_provider_enum = CIProvider(ci_provider)
        provider_config = get_provider_config(ci_provider_enum)
        ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

        # Fetch builds
        fetch_kwargs = {
            "since": since_dt,
            "limit": max_builds,
            "exclude_bots": True,
            "only_with_logs": only_with_logs,
        }
        if ci_provider_enum == CIProvider.GITHUB_ACTIONS and installation_id:
            fetch_kwargs["installation_id"] = installation_id

        # Use sync version of the fetch
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            builds = loop.run_until_complete(
                ci_instance.fetch_builds(full_name, **fetch_kwargs)
            )
        finally:
            loop.close()

        logger.info(f"Fetched {len(builds)} builds from {ci_provider} for {full_name}")
        publish_status(repo_id, "importing", f"Found {len(builds)} builds, saving...")

        # Save builds to database
        saved_count = 0
        build_ids = []

        for build in builds:
            if build.status != BuildStatus.COMPLETED:
                continue

            run_id = build.build_id
            workflow_run_id = int(run_id) if run_id.isdigit() else hash(run_id)

            # Check if already exists
            workflow_run = workflow_run_repo.find_by_repo_and_run_id(
                repo_id, workflow_run_id
            )

            if not workflow_run:
                # Create RawWorkflowRun
                workflow_run = RawWorkflowRun(
                    _id=None,
                    raw_repo_id=ObjectId(repo_id),
                    workflow_run_id=workflow_run_id,
                    head_sha=build.commit_sha,
                    build_number=build.build_number,
                    status=build.status,
                    conclusion=build.conclusion,
                    build_created_at=build.created_at or datetime.now(timezone.utc),
                    build_updated_at=build.created_at or datetime.now(timezone.utc),
                    github_metadata=build.raw_data or {},
                    head_branch=build.branch,
                    duration_seconds=build.duration_seconds,
                    logs_path=None,
                )
                workflow_run = workflow_run_repo.insert_one(workflow_run)
                saved_count += 1

            # Check if ModelTrainingBuild already exists for this workflow_run
            existing_model_build = model_build_repo.find_by_workflow_run(
                ObjectId(repo_id), workflow_run.id
            )

            if not existing_model_build:
                model_build = ModelTrainingBuild(
                    _id=None,
                    raw_repo_id=ObjectId(repo_id),
                    raw_workflow_run_id=workflow_run.id,
                    model_repo_config_id=ObjectId(repo_id),
                    head_sha=build.commit_sha,
                    build_number=build.build_number,
                    build_created_at=build.created_at,
                    build_conclusion=build.conclusion or BuildConclusion.UNKNOWN,
                    extraction_status=ExtractionStatus.PENDING,
                )
                model_build_repo.insert_one(model_build)

            build_ids.append(workflow_run_id)

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


# Task 4: dispatch_processing - Schedule feature extraction in batches
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.dispatch_processing",
    queue="import_repo",
)
def dispatch_processing(
    self: PipelineTask,
    fetch_result: Dict[str, Any],  # Result from fetch_and_save_builds
    repo_id: str,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    Dispatch feature extraction tasks in batches.
    This prevents flooding the queue with thousands of tasks at once.
    """
    import time

    build_ids = fetch_result.get("build_ids", [])

    if not build_ids:
        logger.info(f"No builds to process for repo {repo_id}")

        # Mark as imported anyway
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

        if i + batch_size < len(build_ids):
            time.sleep(0.05)

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
