import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import redis
from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.enums import ExtractionStatus
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.pipeline.feature_dag._metadata import (
    format_features_for_storage,
)
from app.tasks.shared import extract_features_for_build

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


def publish_status(
    repo_id: str, status: str, message: str = "", stats: Optional[Dict[str, int]] = None
):
    """Publish status update to Redis for real-time UI updates."""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        payload = {
            "type": "REPO_UPDATE",
            "payload": {
                "repo_id": repo_id,
                "status": status,
                "message": message,
            },
        }
        if stats:
            payload["payload"]["stats"] = stats

        redis_client.publish("events", json.dumps(payload))

    except Exception as e:
        logger.error(f"Failed to publish status update: {e}")


# Task 1: Orchestrator - starts ingestion then processing
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_processing.start_model_processing",
    queue="processing",
    soft_time_limit=120,
    time_limit=180,
)
def start_model_processing(
    self: PipelineTask,
    repo_config_id: str,
    ci_provider: str,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator: Start ingestion for repo, then dispatch processing.

    Flow: start_model_processing -> ingest_model_builds -> dispatch_build_processing
    """
    from app.entities.enums import ModelImportStatus
    from app.repositories.model_repo_config import ModelRepoConfigRepository
    from app.tasks.model_ingestion import ingest_model_builds

    # Generate correlation_id for tracing entire flow
    correlation_id = str(uuid.uuid4())

    # Set tracing context for structured logging
    TracingContext.set(
        correlation_id=correlation_id,
        repo_id=repo_config_id,
        pipeline_type="model_processing",
    )

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
            ci_provider=ci_provider,
            max_builds=max_builds,
            since_days=since_days,
            only_with_logs=only_with_logs,
            correlation_id=correlation_id,
        )

        logger.info(f"Dispatched model processing workflow for {repo.full_name}")

        return {
            "status": "dispatched",
            "repo_config_id": repo_config_id,
            "full_name": repo.full_name,
            "correlation_id": correlation_id,
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
    soft_time_limit=300,
    time_limit=360,
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

    Looks up ModelImportBuild for each raw_build_run_id to get the
    model_import_build_id reference.

    Flow:
    1. Create ModelTrainingBuild for each raw_build_run (with PENDING status)
    2. Dispatch process_workflow_run tasks in batches
    """

    from celery import chord, group

    from app.entities.enums import ExtractionStatus, ModelImportStatus
    from app.repositories.model_import_build import ModelImportBuildRepository
    from app.repositories.model_repo_config import ModelRepoConfigRepository
    from app.repositories.model_training_build import ModelTrainingBuildRepository
    from app.repositories.raw_build_run import RawBuildRunRepository

    if batch_size is None:
        batch_size = settings.PROCESSING_BUILDS_PER_BATCH

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    import_build_repo = ModelImportBuildRepository(self.db)

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

        # Find ModelImportBuild for this raw_build_run
        import_build = import_build_repo.find_by_business_key(repo_config_id, run_id_str)
        if not import_build:
            logger.warning(f"ModelImportBuild not found for {run_id_str}, skipping")
            continue

        # Check if ModelTrainingBuild already exists
        existing = model_build_repo.find_by_workflow_run(ObjectId(raw_repo_id), run_id)
        if existing:
            logger.debug(f"ModelTrainingBuild already exists for {run_id_str}")
            model_build_ids.append(existing.id)
            continue

        # Create new ModelTrainingBuild with model_import_build_id reference
        model_build = ModelTrainingBuild(
            raw_repo_id=ObjectId(raw_repo_id),
            raw_build_run_id=run_id,
            model_import_build_id=import_build.id,  # Link to import build
            head_sha=raw_build_run.commit_sha,
            build_number=raw_build_run.build_number,
            build_created_at=raw_build_run.created_at,
            extraction_status=ExtractionStatus.PENDING,
        )
        inserted = model_build_repo.insert_one(model_build)
        model_build_ids.append(inserted.id)
        created_count += 1

    logger.info(f"Created {created_count} ModelTrainingBuild documents for repo {repo_config_id}")

    publish_status(
        repo_config_id,
        "importing",
        f"Scheduling {len(model_build_ids)} builds for processing...",
    )

    # Step 2: Dispatch all processing tasks with chord for accurate completion tracking
    processing_tasks = [
        process_workflow_run.si(
            repo_config_id=repo_config_id,
            model_build_id=str(build_id),
        )
        for build_id in model_build_ids
    ]

    # Dispatch chord: all tasks run in parallel, then finalize is called
    chord(
        group(processing_tasks),
        finalize_model_processing.s(repo_config_id=repo_config_id, created_count=created_count),
    ).apply_async()

    logger.info(f"Dispatched chord with {len(model_build_ids)} processing tasks")
    publish_status(
        repo_config_id,
        "processing",
        f"Processing {len(model_build_ids)} builds...",
    )

    return {
        "repo_config_id": repo_config_id,
        "created": created_count,
        "dispatched": len(model_build_ids),
        "status": "processing",
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.finalize_model_processing",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def finalize_model_processing(
    self: PipelineTask,
    results: List[Dict[str, Any]],
    repo_config_id: str,
    created_count: int,
) -> Dict[str, Any]:
    """
    Chord callback: Finalize model processing after all builds are processed.

    Args:
        results: List of results from all process_workflow_run tasks
        repo_config_id: The repository config ID
        created_count: Number of builds created before processing
    """
    from datetime import datetime

    from app.entities.enums import ModelImportStatus

    logger.info(f"Finalizing model processing for {repo_config_id}")

    # Aggregate results
    success_count = sum(1 for r in results if r and r.get("status") == "completed")
    failed_count = sum(1 for r in results if r and r.get("status") == "failed")
    skipped_count = sum(1 for r in results if r and r.get("status") == "skipped")
    total_count = len(results)

    # Determine final status
    if failed_count > 0 and success_count == 0:
        final_status = "failed"
    elif failed_count > 0 and success_count > 0:
        final_status = "partial"
    else:
        final_status = "completed"

    # Mark import as complete
    model_build_repo = ModelTrainingBuildRepository(self.db)
    aggregated_stats = model_build_repo.aggregate_stats_by_repo_config(ObjectId(repo_config_id))

    repo_config_repo = ModelRepoConfigRepository(self.db)
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "import_status": ModelImportStatus.IMPORTED.value,
            "last_sync_status": "success",
            "last_synced_at": datetime.utcnow(),
            "total_builds_processed": aggregated_stats["total_builds_processed"],
            "total_builds_failed": aggregated_stats["total_builds_failed"],
        },
    )

    publish_status(
        repo_config_id,
        "imported" if final_status != "failed" else "failed",
        f"Processed {success_count}/{total_count} builds successfully",
        stats={
            "total_builds_processed": aggregated_stats["total_builds_processed"],
            "total_builds_failed": aggregated_stats["total_builds_failed"],
        },
    )

    return {
        "repo_config_id": repo_config_id,
        "created": created_count,
        "processed": total_count,
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "status": final_status,
        "aggregated_stats": aggregated_stats,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.process_workflow_run",
    queue="processing",
    soft_time_limit=600,
    time_limit=900,
)
def process_workflow_run(
    self: PipelineTask,
    repo_config_id: str,
    model_build_id: str,
    is_reprocess: bool = False,
) -> Dict[str, Any]:
    """
    Process a single build for feature extraction.

    Args:
        repo_config_id: The model_repo_config_id
        model_build_id: The ModelTrainingBuild ObjectId string (already created with PENDING status)
        is_reprocess: If True, skip incrementing build counters (build was already counted)
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
                "extraction_status": ExtractionStatus.FAILED.value,
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

        # Always use TravisTorrent Full template features
        template_repo = DatasetTemplateRepository(self.db)
        template = template_repo.find_by_name("TravisTorrent Full")
        feature_names = template.feature_names if template else []

        # Create GitHub client for GITHUB_API features
        github_client_input = None
        try:
            from app.services.github.github_client import get_public_github_client
            from app.tasks.pipeline.feature_dag._inputs import GitHubClientInput

            client = get_public_github_client()
            github_client_input = GitHubClientInput(client=client, full_name=raw_repo.full_name)
        except Exception as e:
            logger.warning(f"Failed to create GitHub client: {e}")

        # Use shared helper for feature extraction with status
        result = extract_features_for_build(
            db=self.db,
            raw_repo=raw_repo,
            feature_config=repo_config.feature_configs,
            raw_build_run=raw_build_run,
            selected_features=feature_names,
            github_client=github_client_input,
        )

        updates = {}
        raw_features = result.get("features", {})
        updates["features"] = format_features_for_storage(raw_features)
        updates["feature_count"] = len(updates["features"])

        if result["status"] == "completed":
            updates["extraction_status"] = ExtractionStatus.COMPLETED.value
        elif result["status"] == "partial":
            updates["extraction_status"] = ExtractionStatus.PARTIAL.value
        else:
            updates["extraction_status"] = ExtractionStatus.FAILED.value

        # Handle errors and warnings
        if result.get("errors"):
            updates["extraction_error"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["extraction_error"] = "Warning: " + "; ".join(result["warnings"])

        if result.get("is_missing_commit"):
            updates["is_missing_commit"] = True

        # Track missing resources and skipped features (Graceful Degradation)
        if result.get("missing_resources"):
            updates["missing_resources"] = result["missing_resources"]
        if result.get("skipped_features"):
            updates["skipped_features"] = result["skipped_features"]

        model_build_repo.update_one(build_id, updates)

        # Update repo config stats (skip if reprocessing - already counted)
        if not is_reprocess and updates["extraction_status"] in (
            ExtractionStatus.COMPLETED.value,
            ExtractionStatus.PARTIAL.value,
        ):
            updated_config = repo_config_repo.increment_builds_processed(ObjectId(repo_config_id))
            stats = None
            if updated_config:
                stats = {
                    "total_builds_imported": updated_config.total_builds_imported,
                    "total_builds_processed": updated_config.total_builds_processed,
                    "total_builds_failed": updated_config.total_builds_failed,
                }

            # Notify frontend of stats update
            publish_status(
                repo_config_id,
                "processing",
                f"Build {build_id[:8]} completed",
                stats=stats,
            )
        elif not is_reprocess and updates["extraction_status"] == ExtractionStatus.FAILED.value:
            updated_config = repo_config_repo.increment_builds_failed(ObjectId(repo_config_id))
            stats = None
            if updated_config:
                stats = {
                    "total_builds_imported": updated_config.total_builds_imported,
                    "total_builds_processed": updated_config.total_builds_processed,
                    "total_builds_failed": updated_config.total_builds_failed,
                }

            # Notify frontend of stats update
            publish_status(
                repo_config_id,
                "processing",
                f"Build {build_id[:8]} failed",
                stats=stats,
            )

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
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": str(e),
            },
        )

        # Increment failed count
        updated_config = repo_config_repo.increment_builds_failed(ObjectId(repo_config_id))
        stats = None
        if updated_config:
            stats = {
                "total_builds_imported": updated_config.total_builds_imported,
                "total_builds_processed": updated_config.total_builds_processed,
                "total_builds_failed": updated_config.total_builds_failed,
            }

        # Notify frontend of stats update
        publish_status(
            repo_config_id,
            "processing",
            f"Build {build_id[:8]} failed",
            stats=stats,
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
    soft_time_limit=600,
    time_limit=900,
)
def reprocess_build(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Reprocess an existing model build with the pipeline.

    Useful for:
    - Retrying failed builds
    - Extracting new features after pipeline updates
    - Testing pipeline changes on existing data
    """
    # Generate new correlation_id for reprocessing
    correlation_id = str(uuid.uuid4())
    TracingContext.set(
        correlation_id=correlation_id,
        pipeline_type="model_reprocess",
    )

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
    process_workflow_run.delay(
        repo_config_id, build_id, is_reprocess=True, correlation_id=correlation_id
    )

    return {
        "status": "queued",
        "build_id": build_id,
        "correlation_id": correlation_id,
        "message": f"Build {build_id} queued for reprocessing",
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.reprocess_repo_builds",
    queue="processing",
    soft_time_limit=300,
    time_limit=360,
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
    # Generate new correlation_id for this batch reprocessing
    correlation_id = str(uuid.uuid4())
    TracingContext.set(
        correlation_id=correlation_id,
        repo_id=repo_config_id,
        pipeline_type="model_batch_reprocess",
    )

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate repository exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    # Find all builds for this repository
    builds, _ = model_build_repo.list_by_repo(repo_config_id, limit=0)  # limit=0 means all
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
            process_workflow_run.delay(repo_config_id, str(build.id), correlation_id=correlation_id)
            queued_count += 1
        except Exception as e:
            logger.warning(f"Failed to queue build {build.id} for reprocessing: {e}")

    logger.info(f"Queued {queued_count} builds for reprocessing in repository {repo_config_id}")

    return {
        "status": "queued",
        "builds_queued": queued_count,
        "total_builds": len(builds),
        "correlation_id": correlation_id,
    }
