"""
Build Processing Tasks using the new DAG-based Feature Pipeline.

This module uses the Hamilton-based pipeline directly for feature extraction.
"""

from typing import List
from app.ci_providers.models import CIProvider
from app.entities.model_training_build import ModelTrainingBuild
from app.entities.enums import ExtractionStatus, ModelBuildConclusion
from app.entities.pipeline_run import PipelineCategory
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from bson import ObjectId
import redis
import json

from app.celery_app import celery_app
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.shared import extract_features_for_build
from app.config import settings
from app.paths import REPOS_DIR
from app.tasks.pipeline.feature_dag._metadata import (
    format_features_for_storage,
)
from app.repositories.dataset_template_repository import DatasetTemplateRepository

logger = logging.getLogger(__name__)


def publish_build_update(repo_id: str, build_id: str, status: str):
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.publish(
            "events",
            json.dumps(
                {
                    "type": "BUILD_UPDATE",
                    "payload": {
                        "repo_id": repo_id,
                        "build_id": build_id,
                        "status": status,
                    },
                }
            ),
        )
    except Exception as e:
        logger.error(f"Failed to publish build update: {e}")


def publish_status(repo_id: str, status: str, message: str = ""):
    """Publish status update to Redis for real-time UI updates."""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
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


# Task 1: Orchestrator - starts ingestion then processing
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_processing.start_model_processing",
    queue="processing",
)
def start_model_processing(
    self: PipelineTask,
    repo_config_id: str,
    installation_id: str,
    ci_provider: str,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator: Start ingestion for repo, then dispatch processing.

    Flow: start_model_processing -> ingest_model_builds -> dispatch_build_processing
    """
    from celery import chain
    from app.tasks.model_ingestion import ingest_model_builds
    from app.repositories.model_repo_config import ModelRepoConfigRepository
    from app.entities.enums import ModelImportStatus

    model_repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate repo exists
    repo = model_repo_config_repo.find_by_id(repo_config_id)
    if not repo:
        logger.error(f"Repository {repo_config_id} not found")
        return {"status": "error", "error": "Repository not found"}

    # Mark as started
    model_repo_config_repo.update_repository(
        repo_config_id,
        {"import_status": ModelImportStatus.IMPORTING.value},
    )
    publish_status(repo_config_id, "importing", "Starting import workflow...")

    try:
        ingest_model_builds.delay(
            repo_config_id=repo_config_id,
            installation_id=installation_id,
            ci_provider=ci_provider,
            max_builds=max_builds,
            since_days=since_days,
            only_with_logs=only_with_logs,
        )

        logger.info(f"Dispatched model processing workflow for {repo.full_name}")

        return {
            "status": "dispatched",
            "repo_config_id": repo_config_id,
            "full_name": repo.full_name,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Model processing start failed: {error_msg}")
        model_repo_config_repo.update_repository(
            repo_config_id,
            {
                "import_status": ModelImportStatus.FAILED.value,
                "last_sync_error": error_msg,
            },
        )
        publish_status(repo_config_id, "failed", error_msg)
        raise


# Task 2: Dispatch processing for all pending builds
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_processing.dispatch_build_processing",
    queue="processing",
)
def dispatch_build_processing(
    self: PipelineTask,
    repo_config_id: str,
    raw_repo_id: str,
    raw_build_run_ids: List[str],
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create ModelTrainingBuild docs and dispatch feature extraction tasks.

    Called by finalize_ingestion with the list of raw_build_run IDs.

    Flow:
    1. Create ModelTrainingBuild for each raw_build_run (with PENDING status)
    2. Dispatch process_workflow_run tasks in batches
    """
    import time
    from celery import group
    from app.repositories.model_training_build import ModelTrainingBuildRepository
    from app.repositories.model_repo_config import ModelRepoConfigRepository
    from app.repositories.raw_build_run import RawBuildRunRepository
    from app.entities.model_training_build import ModelTrainingBuild
    from app.entities.enums import ExtractionStatus, ModelImportStatus

    if batch_size is None:
        batch_size = settings.PROCESSING_BATCH_SIZE

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)

    if not raw_build_run_ids:
        logger.info(f"No builds to process for repo config {repo_config_id}")
        repo_config_repo.update_repository(
            repo_config_id,
            {"import_status": ModelImportStatus.IMPORTED.value},
        )
        publish_status(repo_config_id, "imported", "No new builds to process")
        return {"repo_config_id": repo_config_id, "dispatched": 0}

    # Step 1: Create ModelTrainingBuild for each raw_build_run
    created_count = 0
    model_build_ids = []

    for run_id_str in raw_build_run_ids:
        run_id = ObjectId(run_id_str)

        # Get the build run details
        raw_build_run = raw_build_run_repo.find_by_id(run_id)
        if not raw_build_run:
            logger.warning(f"RawBuildRun {run_id_str} not found, skipping")
            continue

        # Check if ModelTrainingBuild already exists
        existing = model_build_repo.find_by_workflow_run(ObjectId(raw_repo_id), run_id)
        if existing:
            logger.debug(f"ModelTrainingBuild already exists for {run_id_str}")
            model_build_ids.append(existing.id)
            continue

        # Create new ModelTrainingBuild with PENDING status
        model_build = ModelTrainingBuild(
            raw_repo_id=ObjectId(raw_repo_id),
            raw_build_run_id=run_id,
            model_repo_config_id=ObjectId(repo_config_id),
            head_sha=raw_build_run.commit_sha,
            build_number=raw_build_run.build_number,
            build_created_at=raw_build_run.created_at,
            extraction_status=ExtractionStatus.PENDING,
        )
        inserted = model_build_repo.insert_one(model_build)
        model_build_ids.append(inserted.id)
        created_count += 1

    logger.info(
        f"Created {created_count} ModelTrainingBuild documents for repo {repo_config_id}"
    )

    publish_status(
        repo_config_id,
        "importing",
        f"Scheduling {len(model_build_ids)} builds for processing...",
    )

    # Step 2: Dispatch processing tasks in batches
    dispatched = 0

    for i in range(0, len(model_build_ids), batch_size):
        batch = model_build_ids[i : i + batch_size]

        # Create a group of tasks for this batch
        tasks = group(
            [
                process_workflow_run.s(
                    repo_config_id=repo_config_id,
                    model_build_id=str(build_id),
                )
                for build_id in batch
            ]
        )
        tasks.apply_async()

        dispatched += len(batch)
        logger.info(f"Dispatched batch {i // batch_size + 1}: {len(batch)} tasks")

        # Delay between batches to prevent queue flooding
        if i + batch_size < len(model_build_ids):
            time.sleep(1.0)

    # Mark import as complete
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "import_status": ModelImportStatus.IMPORTED.value,
            "last_sync_status": "success",
        },
    )

    publish_status(
        repo_config_id, "imported", f"Dispatched {dispatched} builds for processing"
    )

    return {
        "repo_config_id": repo_config_id,
        "created": created_count,
        "dispatched": dispatched,
        "status": "completed",
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.process_workflow_run",
    queue="processing",
)
def process_workflow_run(
    self: PipelineTask, repo_config_id: str, model_build_id: str
) -> Dict[str, Any]:
    """
    Process a single build for feature extraction.

    Args:
        repo_config_id: The model_repo_config_id
        model_build_id: The ModelTrainingBuild ObjectId string (already created with PENDING status)
    """
    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)

    # Find the ModelTrainingBuild (already created with PENDING status)
    model_build = model_build_repo.find_one(
        {
            "_id": ObjectId(model_build_id),
            "extraction_status": ExtractionStatus.PENDING.value,
        }
    )
    if not model_build:
        logger.error(f"ModelTrainingBuild not found for id {model_build_id}")
        return {"status": "error", "message": "ModelTrainingBuild not found"}

    # Get the RawBuildRun
    raw_build_run = raw_build_run_repo.find_by_id(model_build.raw_build_run_id)
    if not raw_build_run:
        logger.error(f"RawBuildRun not found for id {model_build.raw_build_run_id}")
        model_build_repo.update_one(
            model_build_id,
            {
                "extraction_status": ExtractionStatus.FAILED,
                "extraction_error": "RawBuildRun not found",
            },
        )
        return {"status": "error", "message": "RawBuildRun not found"}

    # Validate repository exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    build_id = str(model_build.id)

    # Notify clients that processing started
    publish_build_update(repo_config_id, build_id, "in_progress")

    try:
        # Fetch RawRepository for RepoInput
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
        if not raw_repo:
            logger.error(f"RawRepository {repo_config.raw_repo_id} not found")
            return {"status": "error", "message": "RawRepository not found"}

        # Get feature names from template
        template_repo = DatasetTemplateRepository(self.db)
        template = template_repo.find_by_name("TravisTorrent Full")
        feature_names = template.feature_names if template else []

        # Use shared helper for feature extraction with status
        result = extract_features_for_build(
            db=self.db,
            raw_repo=raw_repo,
            repo_config=repo_config,
            build_run=raw_build_run,
            selected_features=feature_names,
        )

        updates = {}
        raw_features = result.get("features", {})
        updates["features"] = format_features_for_storage(raw_features)

        if result["status"] == "completed":
            updates["extraction_status"] = ExtractionStatus.COMPLETED
        elif result["status"] == "partial":
            updates["extraction_status"] = ExtractionStatus.PARTIAL
        else:
            updates["extraction_status"] = ExtractionStatus.FAILED

        # Handle errors and warnings
        if result.get("errors"):
            updates["error_message"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["error_message"] = "Warning: " + "; ".join(result["warnings"])

        if result.get("is_missing_commit"):
            updates["is_missing_commit"] = True

        model_build_repo.update_one(build_id, updates)

        publish_build_update(repo_config_id, build_id, updates["extraction_status"])

        logger.info(
            f"Pipeline completed for build {build_id}: "
            f"status={result['status']}, "
            f"features={result.get('feature_count', 0)}"
        )

        return {
            "status": result["status"],
            "build_id": build_id,
            "feature_count": result.get("feature_count", 0),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
        }

    except Exception as e:
        logger.error(f"Pipeline failed for build {build_id}: {e}", exc_info=True)

        model_build_repo.update_one(
            build_id,
            {
                "extraction_status": ExtractionStatus.FAILED,
                "error_message": str(e),
            },
        )

        publish_build_update(repo_config_id, build_id, "failed")

        return {
            "status": "failed",
            "build_id": build_id,
            "error": str(e),
        }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.reprocess_build",
    queue="processing",
)
def reprocess_build(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Reprocess an existing model build with the pipeline.

    Useful for:
    - Retrying failed builds
    - Extracting new features after pipeline updates
    - Testing pipeline changes on existing data
    """
    model_build_repo = ModelTrainingBuildRepository(self.db)
    model_build = model_build_repo.find_by_id(ObjectId(build_id))
    if not model_build:
        logger.error(f"ModelTrainingBuild {build_id} not found")
        return {"status": "error", "message": "ModelTrainingBuild not found"}

    # Reset to PENDING so process_workflow_run can pick it up
    model_build_repo.update_one(
        build_id,
        {
            "extraction_status": ExtractionStatus.PENDING.value,
            "extraction_error": None,
        },
    )

    repo_config_id = str(model_build.model_repo_config_id)
    process_workflow_run.delay(repo_config_id, build_id)

    return {
        "status": "queued",
        "build_id": build_id,
        "message": f"Build {build_id} queued for reprocessing",
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.reprocess_repo_builds",
    queue="processing",
)
def reprocess_repo_builds(self: PipelineTask, repo_config_id: str) -> Dict[str, Any]:
    """
    Reprocess ALL builds for a repository to re-extract features.

    This is useful when:
    - Feature extractors have been updated/fixed
    - New features have been added
    - Existing builds need their features recalculated

    Unlike import_repo (which fetches new workflow runs from GitHub),
    this task only reprocesses existing builds in the database.
    """
    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate repository exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    # Find all builds for this repository
    builds, _ = model_build_repo.list_by_repo(
        repo_config_id, limit=0
    )  # limit=0 means all
    if not builds:
        logger.info(f"No builds found for repository {repo_config_id}")
        return {
            "status": "completed",
            "builds_queued": 0,
            "message": "No builds to reprocess",
        }

    # Reset all builds to PENDING and queue for reprocessing
    queued_count = 0
    for build in builds:
        try:
            # Reset to PENDING so process_workflow_run can pick it up
            model_build_repo.update_one(
                str(build.id),
                {
                    "extraction_status": ExtractionStatus.PENDING.value,
                    "extraction_error": None,
                },
            )
            process_workflow_run.delay(repo_config_id, str(build.id))
            queued_count += 1
        except Exception as e:
            logger.warning(f"Failed to queue build {build.id} for reprocessing: {e}")

    logger.info(
        f"Queued {queued_count} builds for reprocessing in repository {repo_config_id}"
    )

    return {
        "status": "queued",
        "builds_queued": queued_count,
        "total_builds": len(builds),
    }
