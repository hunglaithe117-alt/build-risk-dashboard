import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.enums import ExtractionStatus
from app.entities.feature_audit_log import AuditLogCategory
from app.entities.model_repo_config import ModelImportStatus
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.repositories.model_import_build import ModelImportBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import ModelPipelineTask
from app.tasks.shared import extract_features_for_build
from app.tasks.shared.events import publish_build_status as publish_build_update
from app.tasks.shared.events import publish_repo_status as publish_status
from app.tasks.shared.processing_tracker import ProcessingTracker

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
    self: ModelPipelineTask,
    repo_config_id: str,
) -> Dict[str, Any]:
    """
    Phase 2: Start processing phase (manually triggered by user).

    Uses ObjectId checkpoint to determine which builds haven't been processed:
    - If last_processed_import_build_id exists: only process builds with _id > checkpoint
    - If no checkpoint: process ALL INGESTED builds (first processing)

    After processing dispatched, updates checkpoint to the last build ID.
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
    # Use ObjectId checkpoint to find only NEW builds since last processing
    # Include both INGESTED and FAILED builds (graceful failure handling)
    last_checkpoint_id = repo_config.last_processed_import_build_id

    if last_checkpoint_id:
        logger.info(f"{log_ctx} Checkpoint exists at {last_checkpoint_id}, finding new builds")
    else:
        logger.info(f"{log_ctx} No checkpoint, processing all builds")

    # Get unprocessed builds (both INGESTED and FAILED, sorted by _id ascending)
    pending_builds = import_build_repo.find_unprocessed_builds(
        repo_config_id, after_id=last_checkpoint_id, include_failed=True
    )

    if not pending_builds:
        logger.info(f"{log_ctx} No new builds to process for {repo_config_id}")
        return {"status": "completed", "builds": 0, "message": "No new builds to process"}

    # Get the last build ID for checkpoint update (will be set AFTER processing)
    last_build_id = pending_builds[-1].id

    # Count statuses
    ingested_count = sum(1 for b in pending_builds if b.status == "ingested")
    failed_count = sum(1 for b in pending_builds if b.status == "failed")

    logger.info(
        f"{log_ctx} Processing {len(pending_builds)} builds "
        f"({ingested_count} ingested, {failed_count} failed), "
        f"checkpoint will be set to {last_build_id} after completion"
    )

    # Extract raw_build_run_ids
    raw_build_run_ids = [str(b.raw_build_run_id) for b in pending_builds]

    # Update status to PROCESSING only (checkpoint set AFTER processing completes)
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSING.value},
    )

    # Dispatch processing with last_build_id for checkpoint update after completion
    dispatch_build_processing.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        raw_build_run_ids=raw_build_run_ids,
        correlation_id=correlation_id,
        last_import_build_id=str(last_build_id),  # NEW: for checkpoint update
    )

    logger.info(f"{log_ctx} Dispatched processing for {len(raw_build_run_ids)} builds")

    publish_status(
        repo_config_id,
        "processing",
        f"Processing {len(raw_build_run_ids)} builds...",
    )

    return {
        "status": "dispatched",
        "builds": len(raw_build_run_ids),
        "ingested": ingested_count,
        "failed": failed_count,
        "pending_checkpoint_id": str(last_build_id),
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
    self: ModelPipelineTask,
    repo_config_id: str,
    raw_repo_id: str,
    raw_build_run_ids: List[str],
    correlation_id: str = "",
    last_import_build_id: str = "",  # NEW: for checkpoint update after completion
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
            repo_config_id=repo_config_id,
            created_count=created_count,
            correlation_id=correlation_id,
            last_import_build_id=last_import_build_id,  # NEW: for checkpoint
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
    self: ModelPipelineTask,
    repo_config_id: str,
    created_count: int,
    correlation_id: str = "",
    last_import_build_id: str = "",  # NEW: to set checkpoint after completion
) -> Dict[str, Any]:
    """
    Finalize model processing after all builds are processed.

    Aggregates results from Redis tracker (per correlation_id) and dispatches prediction.
    Sets checkpoint AFTER processing completes (not before).

    Args:
        repo_config_id: The repository config ID
        created_count: Number of builds created before processing
        correlation_id: Correlation ID for tracing
        last_import_build_id: The last ModelImportBuild ID to set as checkpoint
    """

    from app.entities.model_repo_config import ModelImportStatus

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(f"{corr_prefix} Finalizing model processing for {repo_config_id}")

    # Get results from Redis tracker (scoped to this processing batch)
    tracker = ProcessingTracker(self.redis, repo_config_id, correlation_id)
    tracker_results = tracker.get_results()

    success_count = tracker_results["success_count"]
    failed_count = tracker_results["failed_count"]
    skipped_count = tracker_results["skipped_count"]
    builds_for_prediction = tracker_results["builds_for_prediction"]
    total_count = success_count + failed_count + skipped_count

    logger.info(
        f"{corr_prefix} Processing results from tracker: "
        f"success={success_count}, failed={failed_count}, skipped={skipped_count}"
    )

    # Determine final status - always PROCESSED
    # FAILED is only set by ModelPipelineTask on unhandled exceptions
    final_status = ModelImportStatus.PROCESSED

    # Log warning if all builds failed (but don't set FAILED status)
    if failed_count > 0 and success_count == 0:
        logger.warning(f"{corr_prefix} All builds failed processing ({failed_count})")

    # Update repo config status and SET CHECKPOINT NOW (after processing completes)
    model_build_repo = ModelTrainingBuildRepository(self.db)
    aggregated_stats = model_build_repo.aggregate_stats_by_repo_config(ObjectId(repo_config_id))

    repo_config_repo = ModelRepoConfigRepository(self.db)
    update_data = {
        "status": final_status.value,
        "last_synced_at": datetime.utcnow(),
        "builds_processing_failed": aggregated_stats["builds_processing_failed"],
    }

    # Set checkpoint ONLY after successful processing
    if last_import_build_id:
        update_data["last_processed_import_build_id"] = ObjectId(last_import_build_id)
        logger.info(f"{corr_prefix} Setting checkpoint to {last_import_build_id}")

    repo_config_repo.update_repository(repo_config_id, update_data)

    publish_status(
        repo_config_id,
        final_status.value,
        f"Extracted features from {success_count}/{total_count} builds, starting prediction...",
        stats={
            "builds_processing_failed": failed_count,
        },
    )

    # Dispatch batch prediction using build IDs from Redis tracker
    if builds_for_prediction:
        from celery import group

        batch_size = settings.PREDICTION_BUILDS_PER_BATCH
        batches = [
            builds_for_prediction[i : i + batch_size]
            for i in range(0, len(builds_for_prediction), batch_size)
        ]

        logger.info(
            f"{corr_prefix} Dispatching {len(batches)} prediction batches "
            f"({len(builds_for_prediction)} builds, batch_size={batch_size})"
        )

        # Run all prediction batches in parallel
        prediction_tasks = [predict_builds_batch.si(repo_config_id, batch) for batch in batches]
        group(prediction_tasks).apply_async()

    # Cleanup Redis tracker keys
    tracker.cleanup()

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
    base=ModelPipelineTask,
    name="app.tasks.processing.process_workflow_run",
    queue="processing",
    soft_time_limit=600,
    time_limit=900,
)
def process_workflow_run(
    self: ModelPipelineTask,
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
            category=AuditLogCategory.MODEL_TRAINING,
            model_repo_config_id=repo_config_id,
            output_build_id=build_id,
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
            repo_config_repo.increment_builds_processing_failed(ObjectId(repo_config_id))
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

        # Track result in Redis for finalize aggregation
        if correlation_id:
            tracker = ProcessingTracker(self.redis, repo_config_id, correlation_id)
            if result["status"] in ("completed", "partial"):
                tracker.record_success(build_id)
            else:
                tracker.record_failure(build_id)

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
        updated_config = repo_config_repo.increment_builds_processing_failed(
            ObjectId(repo_config_id)
        )
        stats = None
        if updated_config:
            stats = {
                "builds_completed": updated_config.builds_completed,
                "builds_processing_failed": updated_config.builds_processing_failed,
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
    base=ModelPipelineTask,
    name="app.tasks.processing.retry_failed_builds",
    queue="processing",
    soft_time_limit=300,
    time_limit=360,
)
def retry_failed_builds(self: ModelPipelineTask, repo_config_id: str) -> Dict[str, Any]:
    """
    Retry for failed builds - handles both extraction and prediction failures.

    Logic:
    1. Extraction FAILED builds → full pipeline (extract + predict)
    2. Extraction COMPLETED + Prediction FAILED → predict only (skip extraction)

    This is efficient because it doesn't re-extract features that are already available.
    """
    from celery import chain, group

    correlation_id = str(uuid.uuid4())
    TracingContext.set(
        correlation_id=correlation_id,
        repo_id=repo_config_id,
        pipeline_type="retry_failed",
    )

    corr_prefix = f"[corr={correlation_id[:8]}]"
    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Validate repository exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"{corr_prefix} Repository Config {repo_config_id} not found")
        return {"status": "error", "message": "Repository Config not found"}

    # === GROUP 1: Extraction failed → need full pipeline ===
    extraction_failed_builds = model_build_repo.find_failed_builds(ObjectId(repo_config_id))
    extraction_failed_builds.sort(key=lambda b: b.build_created_at or b.created_at)

    # === GROUP 2: Extraction OK but prediction failed → predict only ===
    prediction_failed_builds = model_build_repo.find_builds_with_failed_predictions(
        ObjectId(repo_config_id)
    )

    extraction_count = len(extraction_failed_builds)
    prediction_count = len(prediction_failed_builds)

    if extraction_count == 0 and prediction_count == 0:
        logger.info(f"{corr_prefix} No failed builds found for repository {repo_config_id}")
        return {
            "status": "completed",
            "extraction_failed": 0,
            "prediction_failed": 0,
            "message": "No failed builds to retry",
        }

    logger.info(
        f"{corr_prefix} Found {extraction_count} extraction failures, "
        f"{prediction_count} prediction failures"
    )

    # Initialize tracker for this retry batch
    tracker = ProcessingTracker(self.redis, repo_config_id, correlation_id)
    tracker.initialize(extraction_count)

    # Update repo status
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSING.value},
    )
    publish_status(
        repo_config_id,
        "processing",
        f"Retrying: {extraction_count} extraction + {prediction_count} prediction failures...",
    )

    # === PROCESS GROUP 1: Reset and re-extract ===
    extraction_build_ids = []
    for build in extraction_failed_builds:
        try:
            model_build_repo.update_one(
                str(build.id),
                {
                    "extraction_status": ExtractionStatus.PENDING.value,
                    "extraction_error": None,
                },
            )
            extraction_build_ids.append(str(build.id))
        except Exception as e:
            logger.warning(f"{corr_prefix} Failed to reset build {build.id}: {e}")

    # === PROCESS GROUP 2: Reset prediction only ===
    prediction_only_ids = []
    for build in prediction_failed_builds:
        try:
            model_build_repo.update_one(
                str(build.id),
                {
                    "prediction_status": ExtractionStatus.PENDING.value,
                    "prediction_error": None,
                    "predicted_label": None,
                },
            )
            prediction_only_ids.append(str(build.id))
        except Exception as e:
            logger.warning(f"{corr_prefix} Failed to reset prediction for {build.id}: {e}")

    # === DISPATCH TASKS ===
    tasks_dispatched = 0

    # Dispatch extraction chain (sequential for temporal features)
    if extraction_build_ids:
        processing_tasks = [
            process_workflow_run.si(
                repo_config_id=repo_config_id,
                model_build_id=build_id,
                is_reprocess=True,
                correlation_id=correlation_id,
            )
            for build_id in extraction_build_ids
        ]

        # Chain: B1 → B2 → ... → finalize
        workflow = chain(
            *processing_tasks,
            finalize_model_processing.si(
                repo_config_id=repo_config_id,
                created_count=len(extraction_build_ids),
                correlation_id=correlation_id,
            ),
        )
        workflow.apply_async()
        tasks_dispatched += len(extraction_build_ids)
        logger.info(f"{corr_prefix} Dispatched {len(extraction_build_ids)} extraction tasks")

    # Dispatch prediction batch (parallel - no temporal dependency)
    if prediction_only_ids:
        # Dispatch prediction in batches
        batch_size = settings.PREDICTION_BUILDS_PER_BATCH
        batches = [
            prediction_only_ids[i : i + batch_size]
            for i in range(0, len(prediction_only_ids), batch_size)
        ]
        prediction_tasks = [predict_builds_batch.si(repo_config_id, batch) for batch in batches]
        group(prediction_tasks).apply_async()
        tasks_dispatched += len(prediction_only_ids)
        logger.info(
            f"{corr_prefix} Dispatched {len(prediction_only_ids)} prediction-only builds "
            f"in {len(batches)} batches"
        )

    return {
        "status": "queued",
        "extraction_retries": len(extraction_build_ids),
        "prediction_retries": len(prediction_only_ids),
        "total_dispatched": tasks_dispatched,
        "correlation_id": correlation_id,
    }


# PROCESSING CHAIN ERROR HANDLER
@celery_app.task(
    bind=True,
    base=ModelPipelineTask,
    name="app.tasks.processing.handle_processing_chain_error",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def handle_processing_chain_error(
    self: ModelPipelineTask,
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


# PREDICTION TASK
@celery_app.task(
    bind=True,
    base=ModelPipelineTask,
    name="app.tasks.processing.predict_builds_batch",
    queue="prediction",
    soft_time_limit=300,
    time_limit=360,
)
def predict_builds_batch(
    self: ModelPipelineTask,
    repo_config_id: str,
    model_build_ids: List[str],
) -> Dict[str, Any]:
    """
    Batch prediction for multiple builds.
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

        for build_id in model_build_ids:
            model_build = model_build_repo.find_by_id(ObjectId(build_id))
            if not model_build:
                continue
            if model_build.predicted_label and not model_build.prediction_error:
                continue  # Already predicted

            if not model_build.feature_vector_id:
                model_build_repo.update_one(
                    build_id,
                    {
                        "prediction_status": ExtractionStatus.FAILED.value,
                        "prediction_error": "No feature_vector_id available",
                    },
                )
                continue

            feature_vector = feature_vector_repo.find_by_id(model_build.feature_vector_id)
            if not feature_vector or not feature_vector.features:
                model_build_repo.update_one(
                    build_id,
                    {
                        "prediction_status": ExtractionStatus.FAILED.value,
                        "prediction_error": "FeatureVector not found or empty",
                    },
                )
                continue

            # Fetch temporal history for LSTM
            # Model uses seq_len=10, so fetch up to 9 previous builds
            # (current build + 9 history = 10 total in sequence)
            temporal_history = None
            tr_prev_build_id = feature_vector.tr_prev_build
            if tr_prev_build_id:
                try:
                    history_vectors = feature_vector_repo.walk_temporal_chain(
                        raw_repo_id=feature_vector.raw_repo_id,
                        starting_ci_run_id=tr_prev_build_id,
                        max_depth=9,  # seq_len - 1 = 10 - 1 = 9
                    )
                    if history_vectors:
                        temporal_history = [v.features for v in reversed(history_vectors)]
                except Exception as e:
                    logger.warning(f"Failed to fetch temporal history for {build_id}: {e}")

            # Track if this was a previously failed prediction (for retry stats)
            was_previously_failed = model_build.prediction_status == ExtractionStatus.FAILED.value

            builds_to_predict.append(
                {
                    "id": build_id,
                    "features": feature_vector.features,
                    "feature_vector_id": feature_vector.id,
                    "temporal_history": temporal_history,
                    "was_previously_failed": was_previously_failed,
                }
            )

        if not builds_to_predict:
            return {"status": "completed", "processed": 0, "skipped": len(model_build_ids)}

        # Mark all builds as IN_PROGRESS before prediction
        for build_info in builds_to_predict:
            model_build_repo.update_one(
                build_info["id"],
                {"prediction_status": ExtractionStatus.IN_PROGRESS.value},
            )

        # Normalize features BEFORE prediction and save to FeatureVector
        for build_info in builds_to_predict:
            normalized = prediction_service.normalize_features(build_info["features"])
            build_info["normalized_features"] = normalized
            # Save normalized features to FeatureVector (single source of truth)
            feature_vector_repo.update_normalized_features(
                build_info["feature_vector_id"],
                normalized,
            )
            # Also normalize temporal history for consistent scaling
            if build_info["temporal_history"]:
                build_info["normalized_history"] = [
                    prediction_service.normalize_features(h) for h in build_info["temporal_history"]
                ]
            else:
                build_info["normalized_history"] = None

        # Predict with pre-scaled features (skip internal scaling)
        results = []
        for build_info in builds_to_predict:
            result = prediction_service.predict(
                features=build_info["normalized_features"],
                temporal_history=build_info["normalized_history"],
                use_prescaled=True,
            )
            results.append(result)

        # Store results
        succeeded = 0
        failed = 0

        for i, build_info in enumerate(builds_to_predict):
            if i >= len(results):
                failed += 1
                continue

            prediction = results[i]

            updates = {
                "predicted_label": prediction.risk_level,
                "prediction_confidence": prediction.risk_score,
                "prediction_uncertainty": prediction.uncertainty,
                "prediction_model_version": prediction.model_version,
                "predicted_at": datetime.utcnow(),
            }

            if prediction.error:
                updates["prediction_status"] = ExtractionStatus.FAILED.value
                updates["prediction_error"] = prediction.error
                failed += 1
            else:
                updates["prediction_status"] = ExtractionStatus.COMPLETED.value
                updates["prediction_error"] = None
                succeeded += 1

            model_build_repo.update_one(build_info["id"], updates)

            # Publish WebSocket event for real-time UI update
            publish_build_update(
                repo_config_id,
                build_info["id"],
                updates["prediction_status"],
            )

        # Update stats: decrement fails for retried builds, increment for new failures
        retried_success_count = 0
        new_failure_count = 0

        for i, build_info in enumerate(builds_to_predict):
            if i >= len(results):
                continue
            prediction = results[i]
            was_failed = build_info.get("was_previously_failed", False)

            if not prediction.error and was_failed:
                retried_success_count += 1
            elif prediction.error and not was_failed:
                new_failure_count += 1

        # Update repo config stats
        if retried_success_count > 0:
            repo_config_repo.decrement_builds_processing_failed(
                ObjectId(repo_config_id), retried_success_count
            )
        if new_failure_count > 0:
            repo_config_repo.increment_builds_processing_failed(
                ObjectId(repo_config_id), new_failure_count
            )

        # Increment builds_completed for successful predictions
        if succeeded > 0:
            repo_config_repo.increment_builds_completed(ObjectId(repo_config_id), succeeded)

        # Notify UI about repo stats changes
        if retried_success_count > 0 or new_failure_count > 0 or succeeded > 0:
            config = repo_config_repo.find_by_id(repo_config_id)
            if config:
                publish_status(
                    repo_config_id,
                    config.status,
                    stats={
                        "builds_completed": config.builds_completed,
                        "builds_processing_failed": config.builds_processing_failed,
                    },
                )

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
                {
                    "prediction_status": ExtractionStatus.FAILED.value,
                    "prediction_error": "Prediction timed out",
                },
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
                {
                    "prediction_status": ExtractionStatus.FAILED.value,
                    "prediction_error": f"Prediction failed: {str(e)}",
                },
            )
        return {
            "status": "failed",
            "processed": 0,
            "error": str(e),
        }
