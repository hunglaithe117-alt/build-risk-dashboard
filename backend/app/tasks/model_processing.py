import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.enums import ExtractionStatus
from app.entities.model_import_build import ModelImportBuildStatus
from app.entities.model_repo_config import ModelImportStatus
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.repositories.model_import_build import ModelImportBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import ModelPipelineTask, PipelineTask
from app.tasks.shared import extract_features_for_build
from app.tasks.shared.events import publish_build_status as publish_build_update
from app.tasks.shared.events import publish_repo_status as publish_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=ModelPipelineTask,
    name="app.tasks.model_ingestion.start_processing_phase",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def start_processing_phase(
    self: PipelineTask,
    repo_config_id: str,
) -> Dict[str, Any]:
    """
    Phase 2: Start processing phase (manually triggered by user).

    Uses checkpoint to determine which builds haven't been processed yet:
    - If last_checkpoint_at exists: only process builds created AFTER that timestamp
    - If no checkpoint: process ALL INGESTED builds (first processing)

    After processing starts, creates a new checkpoint.
    """
    correlation_id = TracingContext.get_correlation_id() or str(uuid.uuid4())
    log_ctx = f"[corr={correlation_id[:8]}]"

    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate status
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"{log_ctx} Repository config {repo_config_id} not found")
        return {"status": "error", "message": "Repository config not found"}

    # Allow processing when status is INGESTED (ready for processing)
    # or PROCESSED (re-processing after sync)
    valid_statuses = [
        ModelImportStatus.INGESTED.value,
        ModelImportStatus.PROCESSED.value,
    ]
    if repo_config.status not in valid_statuses:
        msg = (
            f"Cannot start processing: status is {repo_config.status}. "
            f"Expected: {valid_statuses}"
        )
        logger.warning(f"{log_ctx} {msg}")
        return {"status": "error", "message": msg}

    # === DETERMINE WHICH BUILDS TO PROCESS ===
    # Use checkpoint to find only NEW builds since last processing
    last_checkpoint = repo_config.last_checkpoint_at

    if last_checkpoint:
        # Process only builds created AFTER the last checkpoint
        logger.info(f"{log_ctx} Checkpoint exists at {last_checkpoint}, finding new builds")
        ingested_builds = import_build_repo.find_ingested_after_checkpoint(
            repo_config_id, checkpoint_at=last_checkpoint
        )
    else:
        # First processing - get ALL ingested builds
        logger.info(f"{log_ctx} No checkpoint, processing all INGESTED builds")
        ingested_builds = import_build_repo.find_by_repo_config(
            repo_config_id, status=ModelImportBuildStatus.INGESTED
        )

    if not ingested_builds:
        logger.info(f"{log_ctx} No new ingested builds to process for {repo_config_id}")
        return {"status": "completed", "builds": 0, "message": "No new builds to process"}

    # === CREATE CHECKPOINT ===
    # Snapshot current stats before processing
    status_counts = import_build_repo.count_by_status(repo_config_id)
    total_fetched = sum(status_counts.values())
    ingested_count = status_counts.get(ModelImportBuildStatus.INGESTED.value, 0)
    failed_ingestion_count = status_counts.get(ModelImportBuildStatus.FAILED.value, 0)

    checkpoint_timestamp = datetime.utcnow()
    current_batch_id = repo_config.current_batch_id

    logger.info(
        f"{log_ctx} Creating checkpoint: "
        f"fetched={total_fetched}, ingested={ingested_count}, failed={failed_ingestion_count}, "
        f"processing {len(ingested_builds)} builds"
    )

    # Extract raw_build_run_ids
    raw_build_run_ids = [str(b.raw_build_run_id) for b in ingested_builds]

    # Save checkpoint and update status to PROCESSING
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "status": ModelImportStatus.PROCESSING.value,
            "last_checkpoint_at": checkpoint_timestamp,
            "checkpoint_stats": {
                "fetched": total_fetched,
                "ingested": ingested_count,
                "failed_ingestion": failed_ingestion_count,
                "batch_id": current_batch_id,
            },
        },
    )

    # Dispatch processing with correlation_id
    dispatch_build_processing.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        raw_build_run_ids=raw_build_run_ids,
        correlation_id=correlation_id,
    )

    logger.info(f"{log_ctx} Dispatched processing for {len(raw_build_run_ids)} new builds")

    publish_status(
        repo_config_id,
        "processing",
        f"Processing {len(raw_build_run_ids)} builds...",
    )

    return {
        "status": "dispatched",
        "builds": len(raw_build_run_ids),
        "checkpoint": {
            "timestamp": checkpoint_timestamp.isoformat(),
            "stats": {
                "fetched": total_fetched,
                "ingested": ingested_count,
                "failed_ingestion": failed_ingestion_count,
            },
        },
    }


# Task 2: Dispatch processing for all pending builds
@celery_app.task(
    bind=True,
    base=ModelPipelineTask,
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
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Create ModelTrainingBuild docs and dispatch feature extraction tasks.

    Looks up ModelImportBuild for each raw_build_run_id to get the
    model_import_build_id reference.

    Flow:
    1. Create ModelTrainingBuild for each raw_build_run (with PENDING status)
    2. Dispatch process_workflow_run tasks in batches
    """
    from celery import chain

    from app.entities.enums import ExtractionStatus
    from app.entities.model_repo_config import ModelImportStatus
    from app.repositories.model_repo_config import ModelRepoConfigRepository
    from app.repositories.model_training_build import ModelTrainingBuildRepository
    from app.repositories.raw_build_run import RawBuildRunRepository

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    import_build_repo = ModelImportBuildRepository(self.db)

    if not raw_build_run_ids:
        logger.info(f"{corr_prefix} No builds to process for repo config {repo_config_id}")
        repo_config_repo.update_repository(
            repo_config_id,
            {"status": ModelImportStatus.PROCESSED.value},
        )
        publish_status(repo_config_id, "processed", "No new builds to process")
        return {"repo_config_id": repo_config_id, "dispatched": 0}

    raw_build_runs = raw_build_run_repo.find_by_ids(raw_build_run_ids)
    build_run_map = {str(r.id): r for r in raw_build_runs}

    ingested_builds = import_build_repo.find_by_raw_build_run_ids(repo_config_id, raw_build_run_ids)

    # Sort by created_at ascending (oldest first) for temporal features
    ingested_builds.sort(
        key=lambda ib: build_run_map.get(str(ib.raw_build_run_id), ib).created_at or ib.created_at
    )

    run_oids = [ObjectId(rid) for rid in raw_build_run_ids if ObjectId.is_valid(rid)]
    existing_builds_map = model_build_repo.find_existing_by_raw_build_run_ids(
        ObjectId(raw_repo_id), run_oids
    )

    # Step 1: Create ModelTrainingBuild for INGESTED builds only (in order)
    created_count = 0
    skipped_existing = 0
    model_build_ids = []

    # Process in temporal order: oldest → newest
    for import_build in ingested_builds:
        run_id_str = str(import_build.raw_build_run_id)

        # O(1) lookup from maps
        raw_build_run = build_run_map.get(run_id_str)
        if not raw_build_run:
            logger.warning(f"{corr_prefix} RawBuildRun {run_id_str} not found, skipping")
            continue

        # Check if already exists and processed
        existing = existing_builds_map.get(run_id_str)
        if existing and existing.extraction_status != ExtractionStatus.PENDING:
            logger.debug(
                f"ModelTrainingBuild already processed ({existing.extraction_status}), "
                f"skipping: {run_id_str}"
            )
            skipped_existing += 1
            continue

        # Atomic upsert - creates if not exists, returns existing if it does
        model_build, was_created = model_build_repo.upsert_or_get(
            raw_repo_id=ObjectId(raw_repo_id),
            raw_build_run_id=ObjectId(run_id_str),
            model_import_build_id=import_build.id,
            model_repo_config_id=ObjectId(repo_config_id),
            head_sha=raw_build_run.commit_sha,
            build_number=raw_build_run.build_number,
            build_created_at=raw_build_run.created_at,
            extraction_status=ExtractionStatus.PENDING,
        )
        model_build_ids.append(model_build.id)
        if was_created:
            created_count += 1

    logger.info(
        f"{corr_prefix} Created {created_count} new builds, "
        f"skipped {skipped_existing} already processed, "
        f"dispatching {len(model_build_ids)} for processing (temporal order)"
    )

    # Update status to PROCESSING - feature extraction begins
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSING.value},
    )
    publish_status(
        repo_config_id,
        "processing",
        f"Scheduling {len(model_build_ids)} builds for sequential processing...",
        stats={
            "builds_ingested": len(raw_build_run_ids),
            "builds_created": created_count,
            "builds_skipped": skipped_existing,
        },
    )

    # Step 2: Sequential processing using chain (oldest → newest)
    # This ensures tr_prev_build is populated correctly for temporal features
    model_build_id_strs = [str(bid) for bid in model_build_ids]
    total_builds = len(model_build_id_strs)

    if total_builds == 0:
        # No builds to process
        repo_config_repo.update_repository(
            repo_config_id,
            {"status": ModelImportStatus.PROCESSED.value},
        )
        publish_status(repo_config_id, "processed", "No pending builds to process")
        return {"repo_config_id": repo_config_id, "dispatched": 0}

    # Create sequential tasks - process builds one by one
    sequential_tasks = [
        process_workflow_run.si(
            repo_config_id=repo_config_id,
            model_build_id=build_id,
            is_reprocess=False,
            correlation_id=correlation_id,
        )
        for build_id in model_build_id_strs
    ]

    logger.info(f"{corr_prefix} Dispatching {total_builds} builds for sequential processing")

    # Chain: B1 → B2 → B3 → ... → finalize
    # Each build processes after the previous one completes
    workflow = chain(
        *sequential_tasks,
        finalize_model_processing.si(
            results=[],  # Results will be aggregated from DB
            repo_config_id=repo_config_id,
            created_count=created_count,
            correlation_id=correlation_id,
        ),
    )

    # Add error callback to handle unexpected chain failures (worker crash, OOM, etc.)
    error_callback = handle_processing_chain_error.s(
        repo_config_id=repo_config_id,
        correlation_id=correlation_id,
    )
    workflow.on_error(error_callback).apply_async()

    publish_status(
        repo_config_id,
        "processing",
        f"Processing {total_builds} builds sequentially (oldest → newest)...",
    )

    return {
        "repo_config_id": repo_config_id,
        "dispatched": total_builds,
    }


@celery_app.task(
    bind=True,
    base=ModelPipelineTask,
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
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Chord callback: Finalize model processing after all builds are processed.

    Args:
        results: List of results from all process_workflow_run tasks
        repo_config_id: The repository config ID
        created_count: Number of builds created before processing
        correlation_id: Correlation ID for tracing
    """

    from app.entities.model_repo_config import ModelImportStatus

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(f"{corr_prefix} Finalizing model processing for {repo_config_id}")

    # Aggregate results
    success_count = sum(1 for r in results if r and r.get("status") == "completed")
    failed_count = sum(1 for r in results if r and r.get("status") == "failed")
    skipped_count = sum(1 for r in results if r and r.get("status") == "skipped")
    total_count = len(results)

    # Determine final status - always PROCESSED
    # FAILED is only set by ModelPipelineTask on unhandled exceptions
    final_status = ModelImportStatus.PROCESSED

    # Log warning if all builds failed (but don't set FAILED status)
    if failed_count > 0 and success_count == 0:
        logger.warning(f"{corr_prefix} All builds failed processing ({failed_count}), ")

    # Mark import as complete
    model_build_repo = ModelTrainingBuildRepository(self.db)
    aggregated_stats = model_build_repo.aggregate_stats_by_repo_config(ObjectId(repo_config_id))

    repo_config_repo = ModelRepoConfigRepository(self.db)
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "status": final_status.value,
            "last_synced_at": datetime.utcnow(),
            "builds_failed": aggregated_stats["builds_failed"],
        },
    )

    publish_status(
        repo_config_id,
        final_status.value,
        f"Extracted features from {success_count}/{total_count} builds, starting prediction...",
        stats={
            "builds_failed": aggregated_stats["builds_failed"],
        },
    )

    # Dispatch batch prediction for all successfully processed builds
    if success_count > 0:
        from celery import group

        # Get IDs of processed builds that need prediction
        builds_for_prediction = model_build_repo.find_builds_needing_prediction(
            ObjectId(repo_config_id)
        )
        if builds_for_prediction:
            build_ids = [str(b.id) for b in builds_for_prediction]
            batch_size = settings.PREDICTION_BUILDS_PER_BATCH

            # Split into batches and dispatch in parallel
            batches = [build_ids[i : i + batch_size] for i in range(0, len(build_ids), batch_size)]

            logger.info(
                f"{corr_prefix} Dispatching {len(batches)} prediction batches "
                f"({len(build_ids)} builds, batch_size={batch_size})"
            )

            # Run all prediction batches in parallel
            prediction_tasks = [predict_builds_batch.si(batch) for batch in batches]
            group(prediction_tasks).apply_async()

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


# Task 4: Process a single build
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
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a single build for feature extraction.

    Args:
        repo_config_id: The model_repo_config_id
        model_build_id: The ModelTrainingBuild ObjectId string
        is_reprocess: If True, skip incrementing build counters
        correlation_id: Correlation ID for tracing
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

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
        logger.error(f"{corr_prefix} ModelTrainingBuild not found for id {model_build_id}")
        return {"status": "error", "message": "ModelTrainingBuild not found"}

    # Get the RawBuildRun
    raw_build_run = raw_build_run_repo.find_by_id(model_build.raw_build_run_id)
    if not raw_build_run:
        logger.error(f"{corr_prefix} RawBuildRun not found for id {model_build.raw_build_run_id}")
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
        logger.error(f"{corr_prefix} Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    build_id = str(model_build.id)

    # Mark as IN_PROGRESS in database
    model_build_repo.update_one(
        build_id,
        {"extraction_status": ExtractionStatus.IN_PROGRESS.value},
    )

    # Notify clients that processing started
    publish_build_update(repo_config_id, build_id, ExtractionStatus.IN_PROGRESS.value)

    try:
        # Fetch RawRepository for RepoInput
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
        if not raw_repo:
            logger.error(f"{corr_prefix} RawRepository {repo_config.raw_repo_id} not found")
            return {"status": "error", "message": "RawRepository not found"}

        # Always use Risk Prediction template features
        template_repo = DatasetTemplateRepository(self.db)
        template = template_repo.find_by_name("Risk Prediction")
        feature_names = template.feature_names if template else []

        # Use shared helper for feature extraction with status
        result = extract_features_for_build(
            db=self.db,
            raw_repo=raw_repo,
            feature_config=repo_config.feature_configs,
            raw_build_run=raw_build_run,
            selected_features=feature_names,
        )

        # Only save reference to FeatureVector (single source of truth for feature data)
        updates = {
            "feature_vector_id": result.get("feature_vector_id"),
        }

        if result["status"] == "completed":
            updates["extraction_status"] = ExtractionStatus.COMPLETED.value
            updates["extracted_at"] = datetime.utcnow()
        elif result["status"] == "partial":
            updates["extraction_status"] = ExtractionStatus.PARTIAL.value
            updates["extracted_at"] = datetime.utcnow()
        else:
            updates["extraction_status"] = ExtractionStatus.FAILED.value

        # Handle errors and warnings
        if result.get("errors"):
            updates["extraction_error"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["extraction_error"] = "Warning: " + "; ".join(result["warnings"])

        model_build_repo.update_one(build_id, updates)

        # Update repo config stats: only track failed builds at extraction time
        # builds_completed is incremented after prediction completes
        if not is_reprocess and updates["extraction_status"] == ExtractionStatus.FAILED.value:
            repo_config_repo.increment_builds_failed(ObjectId(repo_config_id))
            publish_status(
                repo_config_id,
                "processing",
                f"Build {build_id[:8]} failed",
            )

        publish_build_update(repo_config_id, build_id, updates["extraction_status"])

        logger.info(
            f"{corr_prefix} Pipeline completed for build {build_id}: "
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
        logger.error(f"{corr_prefix} Pipeline failed for build {build_id}: {e}", exc_info=True)

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
                "builds_completed": updated_config.builds_completed,
                "builds_failed": updated_config.builds_failed,
            }

        # Notify frontend of stats update
        publish_status(
            repo_config_id,
            "processing",
            f"Build {build_id[:8]} failed - stopping chain (temporal dependency)",
            stats=stats,
        )

        publish_build_update(repo_config_id, build_id, "failed")

        # Re-raise to stop the chain - temporal features depend on previous builds
        # The chain-level error handler will mark remaining IN_PROGRESS builds as FAILED
        raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.reprocess_failed_builds",
    queue="processing",
    soft_time_limit=300,
    time_limit=360,
)
def reprocess_failed_builds(self: PipelineTask, repo_config_id: str) -> Dict[str, Any]:
    """
    Reprocess only FAILED builds for a repository.

    Uses sequential chain to ensure temporal features work correctly.

    This is useful when:
    - Some builds failed due to transient errors (network, rate limits)
    - Feature extractors have been fixed
    - You want to retry only the failed builds, not all builds
    """
    from celery import chain

    correlation_id = str(uuid.uuid4())
    TracingContext.set(
        correlation_id=correlation_id,
        repo_id=repo_config_id,
        pipeline_type="reprocess_failed",
    )

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate repository exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    # Find only FAILED builds
    failed_builds = model_build_repo.find_failed_builds(ObjectId(repo_config_id))
    if not failed_builds:
        logger.info(f"No failed builds found for repository {repo_config_id}")
        return {
            "status": "completed",
            "builds_queued": 0,
            "message": "No failed builds to reprocess",
        }

    # Sort by build_created_at (oldest first) for temporal features
    failed_builds.sort(key=lambda b: b.build_created_at or b.created_at)

    # Reset failed builds to PENDING
    build_ids = []
    for build in failed_builds:
        try:
            model_build_repo.update_one(
                str(build.id),
                {
                    "extraction_status": ExtractionStatus.PENDING.value,
                    "extraction_error": None,
                },
            )
            build_ids.append(str(build.id))
        except Exception as e:
            logger.warning(f"Failed to reset build {build.id}: {e}")

    if not build_ids:
        logger.warning(f"No builds to reprocess for {repo_config_id}")
        return {"status": "error", "message": "Failed to reset builds"}

    # Update repo status to processing
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSING.value},
    )
    publish_status(
        repo_config_id,
        "processing",
        f"Retrying {len(build_ids)} failed builds sequentially...",
        stats={"builds_failed": len(failed_builds)},
    )

    # Build sequential processing tasks (oldest → newest)
    processing_tasks = [
        process_workflow_run.si(
            repo_config_id=repo_config_id,
            model_build_id=build_id,
            is_reprocess=True,
            correlation_id=correlation_id,
        )
        for build_id in build_ids
    ]

    # Sequential chain: B1 → B2 → B3 → ... → finalize
    workflow = chain(
        *processing_tasks,
        finalize_model_processing.si(
            results=[],
            repo_config_id=repo_config_id,
            created_count=len(build_ids),
            correlation_id=correlation_id,
        ),
    )
    workflow.apply_async()

    logger.info(f"Dispatched sequential chain with {len(build_ids)} reprocess tasks")

    return {
        "status": "queued",
        "builds_queued": len(build_ids),
        "total_failed": len(failed_builds),
        "correlation_id": correlation_id,
    }


# PROCESSING CHAIN ERROR HANDLER
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.handle_processing_chain_error",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def handle_processing_chain_error(
    self: PipelineTask,
    request,
    exc,
    traceback,
    repo_config_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Error callback for processing chain failure.

    When processing chain fails:
    1. Mark all IN_PROGRESS builds as FAILED
    2. Update repo config status to PARTIAL (not FAILED)
    3. Allow user to retry failed builds

    Args:
        request: Celery request object
        exc: Exception that caused the failure
        traceback: Traceback string
        repo_config_id: The model repo config ID
        correlation_id: Correlation ID for tracing
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    error_msg = str(exc) if exc else "Unknown processing error"

    logger.error(f"{corr_prefix} Processing chain failed for {repo_config_id}: {error_msg}")

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Mark all IN_PROGRESS builds as FAILED
    in_progress_builds = model_build_repo.find_by_status(
        repo_config_id,
        ExtractionStatus.IN_PROGRESS,
    )

    failed_count = 0
    for build in in_progress_builds:
        model_build_repo.update_one(
            str(build.id),
            {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": f"Chain failed: {error_msg}",
            },
        )
        failed_count += 1

    logger.warning(f"{corr_prefix} Marked {failed_count} IN_PROGRESS builds as FAILED")

    # Check if any builds completed before failure
    completed_builds = model_build_repo.find_by_status(
        repo_config_id,
        ExtractionStatus.COMPLETED,
    )

    if completed_builds:
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "status": ModelImportStatus.PROCESSED.value,
                "error_message": f"Processing had some failures: {error_msg}",
            },
        )
        publish_status(
            repo_config_id,
            ModelImportStatus.PROCESSED.value,
            f"Processing done: {len(completed_builds)} ok, {failed_count} failed. "
            f"Use Retry Failed to retry.",
        )
    else:
        # No builds completed - mark as failed
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "status": ModelImportStatus.FAILED.value,
                "error_message": error_msg,
            },
        )
        publish_status(
            repo_config_id,
            "failed",
            f"Processing failed: {error_msg}. Use Retry Failed to retry.",
        )

    return {
        "status": "handled",
        "failed_builds": failed_count,
        "completed_builds": len(completed_builds) if completed_builds else 0,
        "error": error_msg,
    }


# =============================================================================
# PREDICTION TASK (Batch Only)
# =============================================================================


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.predict_builds_batch",
    queue="prediction",
    soft_time_limit=300,
    time_limit=360,
)
def predict_builds_batch(
    self: PipelineTask,
    model_build_ids: List[str],
) -> Dict[str, Any]:
    """
    Batch prediction for multiple builds.

    More efficient than individual predict calls.
    Fetches features from FeatureVector collection.
    After prediction, increments builds_completed count on repo config.
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from app.repositories.feature_vector import FeatureVectorRepository
    from app.services.prediction_service import PredictionService

    if not model_build_ids:
        return {"status": "completed", "processed": 0}

    try:
        model_build_repo = ModelTrainingBuildRepository(self.db)
        feature_vector_repo = FeatureVectorRepository(self.db)
        repo_config_repo = ModelRepoConfigRepository(self.db)
        prediction_service = PredictionService()

        # Collect features for all builds and track repo config ids
        builds_to_predict = []
        repo_config_ids = set()

        for build_id in model_build_ids:
            model_build = model_build_repo.find_by_id(ObjectId(build_id))
            if not model_build:
                continue
            if model_build.predicted_label and not model_build.prediction_error:
                continue  # Already predicted

            # Fetch features from FeatureVector
            if not model_build.feature_vector_id:
                model_build_repo.update_one(
                    build_id,
                    {"prediction_error": "No feature_vector_id available"},
                )
                continue

            feature_vector = feature_vector_repo.find_by_id(model_build.feature_vector_id)
            if not feature_vector or not feature_vector.features:
                model_build_repo.update_one(
                    build_id,
                    {"prediction_error": "FeatureVector not found or empty"},
                )
                continue

            # Fetch temporal history (5 previous builds) for LSTM
            temporal_history = None
            tr_prev_build_id = feature_vector.tr_prev_build
            if tr_prev_build_id:
                try:
                    history_vectors = feature_vector_repo.walk_temporal_chain(
                        raw_repo_id=feature_vector.raw_repo_id,
                        starting_ci_run_id=tr_prev_build_id,
                        max_depth=5,
                    )
                    if history_vectors:
                        # Convert to list of feature dicts (newest to oldest)
                        temporal_history = [v.features for v in history_vectors]
                except Exception as e:
                    logger.warning(f"Failed to fetch temporal history for {build_id}: {e}")

            builds_to_predict.append(
                {
                    "id": build_id,
                    "features": feature_vector.features,
                    "temporal_history": temporal_history,
                    "repo_config_id": model_build.model_repo_config_id,
                }
            )
            repo_config_ids.add(model_build.model_repo_config_id)

        if not builds_to_predict:
            return {"status": "completed", "processed": 0, "skipped": len(model_build_ids)}

        # Predict with temporal history
        results = []
        for build_info in builds_to_predict:
            result = prediction_service.predict(
                features=build_info["features"],
                temporal_history=build_info["temporal_history"],
            )
            # Normalize features for storage
            normalized = prediction_service.normalize_features(build_info["features"])
            results.append((normalized, result))

        # Store results and count by repo_config
        succeeded = 0
        failed = 0
        completed_by_repo = {}  # repo_config_id -> count of successful predictions

        for i, build_info in enumerate(builds_to_predict):
            if i >= len(results):
                failed += 1
                continue

            normalized, prediction = results[i]

            updates = {
                "normalized_features": normalized,
                "predicted_label": prediction.risk_level,
                "prediction_confidence": prediction.risk_score,
                "prediction_uncertainty": prediction.uncertainty,
                "prediction_model_version": prediction.model_version,
                "predicted_at": datetime.utcnow(),
            }

            if prediction.error:
                updates["prediction_error"] = prediction.error
                failed += 1
            else:
                updates["prediction_error"] = None
                succeeded += 1
                # Track completed by repo config for batch increment
                repo_id = build_info["repo_config_id"]
                completed_by_repo[repo_id] = completed_by_repo.get(repo_id, 0) + 1

            model_build_repo.update_one(build_info["id"], updates)

        # Increment builds_completed for each repo config (batch)
        for repo_config_id, count in completed_by_repo.items():
            repo_config_repo.increment_builds_completed(repo_config_id, count)

        logger.info(f"Batch prediction: {succeeded} succeeded, {failed} failed")

        return {
            "status": "completed",
            "processed": len(builds_to_predict),
            "succeeded": succeeded,
            "failed": failed,
        }

    except SoftTimeLimitExceeded:
        logger.error(f"Prediction batch timed out with {len(model_build_ids)} builds")
        # Mark remaining unprocessed builds with prediction error
        model_build_repo = ModelTrainingBuildRepository(self.db)
        for build_id in model_build_ids:
            model_build_repo.update_one(
                build_id,
                {"prediction_error": "Prediction timed out"},
            )
        return {
            "status": "timeout",
            "processed": 0,
            "error": "Prediction batch timed out",
        }

    except Exception as e:
        logger.error(f"Prediction batch failed: {e}", exc_info=True)
        # Mark all builds with prediction error
        model_build_repo = ModelTrainingBuildRepository(self.db)
        for build_id in model_build_ids:
            model_build_repo.update_one(
                build_id,
                {"prediction_error": f"Prediction failed: {str(e)}"},
            )
        return {
            "status": "failed",
            "processed": 0,
            "error": str(e),
        }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.retry_failed_predictions",
    queue="prediction",
    soft_time_limit=120,
    time_limit=180,
)
def retry_failed_predictions(
    self: PipelineTask,
    repo_config_id: str,
) -> Dict[str, Any]:
    """
    Retry prediction for builds that had prediction errors.

    This task finds all builds with:
    - extraction_status = COMPLETED or PARTIAL (features available)
    - prediction_error != None (previous prediction failed)

    Then clears the error and dispatches batch prediction.

    Returns:
        Dict with status and count of builds queued for retry
    """
    correlation_id = str(uuid.uuid4())
    TracingContext.set(
        correlation_id=correlation_id,
        repo_id=repo_config_id,
        pipeline_type="retry_predictions",
    )

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate repository exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    # Find builds with failed predictions
    failed_builds = model_build_repo.find_builds_with_failed_predictions(ObjectId(repo_config_id))

    if not failed_builds:
        logger.info(f"No builds with failed predictions for {repo_config_id}")
        return {
            "status": "completed",
            "builds_queued": 0,
            "message": "No builds with failed predictions to retry",
        }

    # Clear prediction_error for retry
    build_ids = []
    for build in failed_builds:
        try:
            model_build_repo.update_one(
                str(build.id),
                {
                    "prediction_error": None,
                    "predicted_label": None,
                    "prediction_confidence": None,
                    "prediction_uncertainty": None,
                    "predicted_at": None,
                },
            )
            build_ids.append(str(build.id))
        except Exception as e:
            logger.warning(f"Failed to reset prediction for build {build.id}: {e}")

    if not build_ids:
        return {"status": "completed", "builds_queued": 0}

    # Dispatch batch prediction
    predict_builds_batch.delay(build_ids)

    logger.info(f"Queued {len(build_ids)} builds for prediction retry")

    publish_status(
        repo_config_id,
        "processing",
        f"Retrying prediction for {len(build_ids)} builds...",
    )

    return {
        "status": "queued",
        "builds_queued": len(build_ids),
        "total_failed": len(failed_builds),
        "correlation_id": correlation_id,
    }
