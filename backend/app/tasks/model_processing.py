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
from app.tasks.base import PipelineTask, SafeTask, TaskState
from app.tasks.shared import extract_features_for_build
from app.tasks.shared.events import publish_build_status as publish_build_update
from app.tasks.shared.events import publish_repo_status as publish_status

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_processing.start_processing_phase",
    queue="model_processing",
    soft_time_limit=60,
    time_limit=120,
)
def start_processing_phase(
    self: PipelineTask,
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
        logger.info(
            f"{log_ctx} Checkpoint exists at {last_checkpoint_id}, finding new builds"
        )
    else:
        logger.info(f"{log_ctx} No checkpoint, processing all builds")

    # Get unprocessed builds (both INGESTED and FAILED, sorted by _id ascending)
    pending_builds = import_build_repo.find_unprocessed_builds(
        repo_config_id, after_id=last_checkpoint_id, include_failed=True
    )

    if not pending_builds:
        logger.info(f"{log_ctx} No new builds to process for {repo_config_id}")
        return {
            "status": "completed",
            "builds": 0,
            "message": "No new builds to process",
        }

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
    base=PipelineTask,
    name="app.tasks.model_processing.dispatch_build_processing",
    queue="model_processing",
    soft_time_limit=300,
    time_limit=360,
)
def dispatch_build_processing(
    self: PipelineTask,
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
        logger.info(
            f"{corr_prefix} No builds to process for repo config {repo_config_id}"
        )
        repo_config_repo.update_repository(
            repo_config_id,
            {"status": ModelImportStatus.PROCESSED.value},
        )
        publish_status(repo_config_id, "processed", "No new builds to process")
        return {"repo_config_id": repo_config_id, "dispatched": 0}

    raw_build_runs = raw_build_run_repo.find_by_ids(raw_build_run_ids)
    build_run_map = {str(r.id): r for r in raw_build_runs}

    ingested_builds = import_build_repo.find_by_raw_build_run_ids(
        repo_config_id, raw_build_run_ids
    )

    # Sort by created_at ascending (oldest first) for temporal features
    ingested_builds.sort(
        key=lambda ib: build_run_map.get(str(ib.raw_build_run_id), ib).created_at
        or ib.created_at
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
            logger.warning(
                f"{corr_prefix} RawBuildRun {run_id_str} not found, skipping"
            )
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

    logger.info(
        f"{corr_prefix} Dispatching {total_builds} builds for sequential processing"
    )

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
    base=PipelineTask,
    name="app.tasks.model_processing.finalize_model_processing",
    queue="model_processing",
    soft_time_limit=60,
    time_limit=120,
)
def finalize_model_processing(
    self: PipelineTask,
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

    # Get results from database (not Redis tracker)
    model_build_repo = ModelTrainingBuildRepository(self.db)
    aggregated_stats = model_build_repo.aggregate_stats_by_repo_config(
        ObjectId(repo_config_id)
    )

    # Get counts from aggregated stats
    success_count = aggregated_stats.get("completed", 0) + aggregated_stats.get(
        "partial", 0
    )
    failed_count = aggregated_stats.get("failed", 0)
    total_count = aggregated_stats.get("total", 0)

    logger.info(
        f"{corr_prefix} Processing results from DB: "
        f"success={success_count}, failed={failed_count}, total={total_count}"
    )

    # Log warning if all builds failed (but don't set FAILED status)
    if failed_count > 0 and success_count == 0:
        logger.warning(f"{corr_prefix} All builds failed processing ({failed_count})")

    # Get builds ready for prediction from database
    builds_ready = model_build_repo.find_builds_for_prediction(ObjectId(repo_config_id))
    builds_for_prediction = [str(b.id) for b in builds_ready]

    repo_config_repo = ModelRepoConfigRepository(self.db)
    update_data = {
        "last_synced_at": datetime.utcnow(),
        "builds_processing_failed": aggregated_stats["builds_processing_failed"],
    }

    # Set checkpoint after extraction completes (before prediction)
    if last_import_build_id:
        update_data["last_processed_import_build_id"] = ObjectId(last_import_build_id)
        logger.info(f"{corr_prefix} Setting checkpoint to {last_import_build_id}")

    repo_config_repo.update_repository(repo_config_id, update_data)

    publish_status(
        repo_config_id,
        "processing",
        f"Extracted features from {success_count}/{total_count} builds, starting prediction...",
        stats={
            "builds_processing_failed": failed_count,
        },
    )

    # Dispatch batch prediction using chord (wait for all to complete)
    if builds_for_prediction:
        from celery import chord

        batch_size = settings.PREDICTION_BUILDS_PER_BATCH
        batches = [
            builds_for_prediction[i : i + batch_size]
            for i in range(0, len(builds_for_prediction), batch_size)
        ]

        logger.info(
            f"{corr_prefix} Dispatching {len(batches)} prediction batches "
            f"({len(builds_for_prediction)} builds, batch_size={batch_size})"
        )

        # Use chord: run all predictions in parallel, then call finalize_prediction
        prediction_tasks = [
            predict_builds_batch.si(repo_config_id, batch) for batch in batches
        ]
        callback = finalize_prediction.si(
            repo_config_id=repo_config_id,
            total_builds=len(builds_for_prediction),
            correlation_id=correlation_id,
        )
        chord(prediction_tasks)(callback)
    else:
        # No predictions needed - set status to PROCESSED immediately
        repo_config_repo.update_repository(
            repo_config_id, {"status": ModelImportStatus.PROCESSED.value}
        )
        publish_status(repo_config_id, "processed", "No builds to predict")

    return {
        "repo_config_id": repo_config_id,
        "created": created_count,
        "processed": total_count,
        "success": success_count,
        "failed": failed_count,
        "status": "predicting",
        "aggregated_stats": aggregated_stats,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_processing.finalize_prediction",
    queue="model_prediction",
    soft_time_limit=60,
    time_limit=120,
)
def finalize_prediction(
    self: PipelineTask,
    repo_config_id: str,
    total_builds: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Finalize prediction phase after all prediction batches complete.

    This is the chord callback from finalize_model_processing.
    Sets the repository status to PROCESSED and publishes final status.

    Args:
        repo_config_id: The repository config ID
        total_builds: Total number of builds that were predicted
        correlation_id: Correlation ID for tracing
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(f"{corr_prefix} Finalizing prediction for {repo_config_id}")

    repo_config_repo = ModelRepoConfigRepository(self.db)
    model_build_repo = ModelTrainingBuildRepository(self.db)

    # Count prediction results
    prediction_stats = model_build_repo.aggregate_prediction_stats(
        ObjectId(repo_config_id)
    )
    predicted_count = prediction_stats.get("predicted", 0)
    prediction_failed = prediction_stats.get("failed", 0)

    # Set final status to PROCESSED
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSED.value},
    )

    logger.info(
        f"{corr_prefix} Prediction complete: {predicted_count} predicted, "
        f"{prediction_failed} failed out of {total_builds} total"
    )

    publish_status(
        repo_config_id,
        "processed",
        f"Processing complete: {predicted_count}/{total_builds} builds predicted",
        stats={
            "predicted": predicted_count,
            "prediction_failed": prediction_failed,
        },
    )

    # =========================================================================
    # NOTIFY USERS WITH REPO ACCESS
    # =========================================================================
    try:
        from app.services.notification_service import notify_users_for_repo

        # Get repo details for notification
        repo_config = repo_config_repo.find_by_id(repo_config_id)
        if repo_config and repo_config.raw_repo_id:
            # Count predictions by risk level
            risk_counts = model_build_repo.aggregate_risk_counts(
                ObjectId(repo_config_id)
            )
            high_count = risk_counts.get("HIGH", 0)
            medium_count = risk_counts.get("MEDIUM", 0)
            low_count = risk_counts.get("LOW", 0)

            # Get HIGH risk builds for individual alerts (limit 3)
            high_risk_builds = []
            if high_count > 0:
                high_risk_builds = model_build_repo.find_high_risk_builds(
                    ObjectId(repo_config_id), limit=3
                )

            # Send notifications to all users with access
            notify_users_for_repo(
                db=self.db,
                raw_repo_id=repo_config.raw_repo_id,
                repo_name=repo_config.full_name,
                repo_id=repo_config_id,
                high_risk_builds=[
                    {"build_number": b.build_number} for b in high_risk_builds
                ],
                prediction_summary={
                    "high": high_count,
                    "medium": medium_count,
                    "low": low_count,
                },
            )
            logger.info(
                f"{corr_prefix} Sent notifications: {high_count} HIGH, "
                f"{medium_count} MEDIUM, {low_count} LOW"
            )

            from app.services.notification_service import (
                notify_pipeline_completed_to_admins,
            )

            notify_pipeline_completed_to_admins(
                db=self.db,
                repo_name=repo_config.full_name,
                predicted_count=predicted_count,
                failed_count=prediction_failed,
                high_count=high_count,
                medium_count=medium_count,
                low_count=low_count,
            )
    except Exception as e:
        # Don't fail the task if notifications fail
        logger.warning(f"{corr_prefix} Failed to send user notifications: {e}")

    return {
        "repo_config_id": repo_config_id,
        "status": "processed",
        "predicted": predicted_count,
        "failed": prediction_failed,
        "total": total_builds,
    }


# Task 4: Process a single build
@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.model_processing.process_workflow_run",
    queue="model_processing",
    soft_time_limit=600,
    time_limit=900,
    max_retries=3,
)
def process_workflow_run(
    self: SafeTask,
    repo_config_id: str,
    model_build_id: str,
    is_reprocess: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a single build for feature extraction.

    Uses SafeTask.run_safe() for:
    - SoftTimeLimitExceeded → checkpoint + retry
    - Proper error handling and status updates
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    # Pre-validation (outside run_safe - these are permanent errors)
    model_build = model_build_repo.find_one(
        {
            "_id": ObjectId(model_build_id),
            "extraction_status": ExtractionStatus.PENDING.value,
        }
    )
    if not model_build:
        logger.info(
            f"{corr_prefix} ModelTrainingBuild {model_build_id} not PENDING, skipping"
        )
        return {"status": "skipped", "message": "Not pending or not found"}

    raw_build_run = raw_build_run_repo.find_by_id(model_build.raw_build_run_id)
    if not raw_build_run:
        model_build_repo.update_one(
            model_build_id,
            {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": "RawBuildRun not found",
            },
        )
        return {"status": "error", "message": "RawBuildRun not found"}

    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        return {"status": "error", "message": "Repository Config not found"}

    raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
    if not raw_repo:
        return {"status": "error", "message": "RawRepository not found"}

    build_id = str(model_build.id)

    def _mark_failed(exc: Exception) -> None:
        """Mark build as FAILED and update stats."""
        model_build_repo.update_one(
            build_id,
            {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": str(exc),
            },
        )
        if not is_reprocess:
            repo_config_repo.increment_builds_processing_failed(
                ObjectId(repo_config_id)
            )
        publish_build_update(repo_config_id, build_id, "failed")

    def _work(state: TaskState) -> Dict[str, Any]:
        """Feature extraction work function."""
        if state.phase == "START":
            # Mark as IN_PROGRESS
            model_build_repo.update_one(
                build_id, {"extraction_status": ExtractionStatus.IN_PROGRESS.value}
            )
            publish_build_update(
                repo_config_id, build_id, ExtractionStatus.IN_PROGRESS.value
            )
            state.phase = "EXTRACTING"

        if state.phase == "EXTRACTING":
            # Get template features
            template_repo = DatasetTemplateRepository(self.db)
            template = template_repo.find_by_name("Risk Prediction")
            feature_names = template.feature_names if template else []

            # Extract features
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
            state.meta["result"] = result
            state.phase = "DONE"

        # Update build status
        result = state.meta.get("result", {"status": "failed"})
        updates = {"feature_vector_id": result.get("feature_vector_id")}

        if result["status"] == "completed":
            updates["extraction_status"] = ExtractionStatus.COMPLETED.value
            updates["extracted_at"] = datetime.utcnow()
        elif result["status"] == "partial":
            updates["extraction_status"] = ExtractionStatus.PARTIAL.value
            updates["extracted_at"] = datetime.utcnow()
        else:
            updates["extraction_status"] = ExtractionStatus.FAILED.value

        if result.get("errors"):
            updates["extraction_error"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["extraction_error"] = "Warning: " + "; ".join(result["warnings"])

        model_build_repo.update_one(build_id, updates)

        # Update stats
        if (
            not is_reprocess
            and updates["extraction_status"] == ExtractionStatus.FAILED.value
        ):
            repo_config_repo.increment_builds_processing_failed(
                ObjectId(repo_config_id)
            )

        publish_build_update(repo_config_id, build_id, updates["extraction_status"])

        return {
            "status": result["status"],
            "build_id": build_id,
            "feature_count": result.get("feature_count", 0),
            "errors": result.get("errors", []),
        }

    return self.run_safe(
        job_id=f"{repo_config_id}:{model_build_id}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=None,  # No cleanup needed - DB updates are idempotent
        fail_on_unknown=False,  # Treat unknown errors as transient for retry
    )


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_processing.retry_failed_builds",
    queue="model_processing",
    soft_time_limit=300,
    time_limit=360,
)
def retry_failed_builds(self: PipelineTask, repo_config_id: str) -> Dict[str, Any]:
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
    extraction_failed_builds = model_build_repo.find_failed_builds(
        ObjectId(repo_config_id)
    )
    extraction_failed_builds.sort(key=lambda b: b.build_created_at or b.created_at)

    # === GROUP 2: Extraction OK but prediction failed → predict only ===
    prediction_failed_builds = model_build_repo.find_builds_with_failed_predictions(
        ObjectId(repo_config_id)
    )

    extraction_count = len(extraction_failed_builds)
    prediction_count = len(prediction_failed_builds)

    if extraction_count == 0 and prediction_count == 0:
        logger.info(
            f"{corr_prefix} No failed builds found for repository {repo_config_id}"
        )
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
            logger.warning(
                f"{corr_prefix} Failed to reset prediction for {build.id}: {e}"
            )

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
        logger.info(
            f"{corr_prefix} Dispatched {len(extraction_build_ids)} extraction tasks"
        )

    # Dispatch prediction batch (parallel - no temporal dependency)
    if prediction_only_ids:
        # Dispatch prediction in batches
        batch_size = settings.PREDICTION_BUILDS_PER_BATCH
        batches = [
            prediction_only_ids[i : i + batch_size]
            for i in range(0, len(prediction_only_ids), batch_size)
        ]
        prediction_tasks = [
            predict_builds_batch.si(repo_config_id, batch) for batch in batches
        ]
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
    base=PipelineTask,
    name="app.tasks.model_processing.handle_processing_chain_error",
    queue="model_processing",
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

    logger.error(
        f"{corr_prefix} Processing chain failed for {repo_config_id}: {error_msg}"
    )

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

    # Notify admins about processing failure
    try:
        from app.services.notification_service import notify_pipeline_failed_to_admins

        repo_config = repo_config_repo.find_by_id(repo_config_id)
        repo_name = repo_config.full_name if repo_config else repo_config_id
        notify_pipeline_failed_to_admins(
            db=self.db,
            repo_name=repo_name,
            error_message=f"Processing failed: {error_msg}",
        )
    except Exception as e:
        logger.warning(f"{corr_prefix} Failed to send failure notification: {e}")

    return {
        "status": "handled",
        "failed_builds": failed_count,
        "completed_builds": len(completed_builds) if completed_builds else 0,
        "error": error_msg,
    }


# PREDICTION TASK
@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.model_processing.predict_builds_batch",
    queue="model_prediction",
    soft_time_limit=300,
    time_limit=360,
    max_retries=3,
)
def predict_builds_batch(
    self: SafeTask,
    repo_config_id: str,
    model_build_ids: List[str],
) -> Dict[str, Any]:
    """
    Batch prediction for multiple builds using SafeTask.run_safe() pattern.

    Phases:
    - START: Initialize repos, collect builds to predict
    - NORMALIZING: Mark IN_PROGRESS, normalize features
    - PREDICTING: Run ML prediction
    - STORING: Store results, update stats
    - DONE: Return final result
    """
    from app.repositories.feature_vector import FeatureVectorRepository
    from app.services.prediction_service import PredictionService

    if not model_build_ids:
        return {"status": "completed", "processed": 0}

    # Initialize repositories (available to inner functions)
    model_build_repo = ModelTrainingBuildRepository(self.db)
    feature_vector_repo = FeatureVectorRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    prediction_service = PredictionService()

    def _mark_failed(exc: Exception) -> None:
        """Mark all unprocessed builds as FAILED."""
        for build_id in model_build_ids:
            model_build_repo.collection.update_one(
                {
                    "_id": ObjectId(build_id),
                    "prediction_status": {
                        "$in": [
                            ExtractionStatus.PENDING.value,
                            ExtractionStatus.IN_PROGRESS.value,
                        ]
                    },
                },
                {
                    "$set": {
                        "prediction_status": ExtractionStatus.FAILED.value,
                        "prediction_error": f"Batch prediction failed: {str(exc)}",
                    }
                },
            )

    def _cleanup(state: TaskState) -> None:
        """Reset IN_PROGRESS builds back to PENDING for retry."""
        for build_id in model_build_ids:
            model_build_repo.collection.update_one(
                {
                    "_id": ObjectId(build_id),
                    "prediction_status": ExtractionStatus.IN_PROGRESS.value,
                },
                {
                    "$set": {
                        "prediction_status": ExtractionStatus.PENDING.value,
                        "prediction_error": None,
                    }
                },
            )

    def _work(state: TaskState) -> Dict[str, Any]:
        """Batch prediction work function with phases."""
        # Phase: START - Collect builds to predict
        if state.phase == "START":
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

                feature_vector = feature_vector_repo.find_by_id(
                    model_build.feature_vector_id
                )
                if not feature_vector or not feature_vector.features:
                    model_build_repo.update_one(
                        build_id,
                        {
                            "prediction_status": ExtractionStatus.FAILED.value,
                            "prediction_error": "FeatureVector not found or empty",
                        },
                    )
                    continue

                # Fetch temporal history for LSTM (seq_len=10)
                temporal_history = None
                tr_prev_build_id = feature_vector.tr_prev_build
                if tr_prev_build_id:
                    try:
                        history_vectors = feature_vector_repo.walk_temporal_chain(
                            raw_repo_id=feature_vector.raw_repo_id,
                            starting_ci_run_id=tr_prev_build_id,
                            max_depth=9,
                        )
                        if history_vectors:
                            temporal_history = [
                                v.features for v in reversed(history_vectors)
                            ]
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch temporal history for {build_id}: {e}"
                        )

                was_previously_failed = (
                    model_build.prediction_status == ExtractionStatus.FAILED.value
                )

                builds_to_predict.append(
                    {
                        "id": build_id,
                        "features": feature_vector.features,
                        "feature_vector_id": feature_vector.id,
                        "temporal_history": temporal_history,
                        "was_previously_failed": was_previously_failed,
                    }
                )

            state.meta["builds_to_predict"] = builds_to_predict

            if not builds_to_predict:
                state.phase = "DONE"
                state.meta["result"] = {
                    "status": "completed",
                    "processed": 0,
                    "skipped": len(model_build_ids),
                }
            else:
                state.phase = "NORMALIZING"

        # Phase: NORMALIZING - Mark IN_PROGRESS and normalize features
        if state.phase == "NORMALIZING":
            builds_to_predict = state.meta["builds_to_predict"]

            for build_info in builds_to_predict:
                model_build_repo.update_one(
                    build_info["id"],
                    {"prediction_status": ExtractionStatus.IN_PROGRESS.value},
                )

            for build_info in builds_to_predict:
                normalized = prediction_service.normalize_features(
                    build_info["features"]
                )
                build_info["normalized_features"] = normalized
                feature_vector_repo.update_normalized_features(
                    build_info["feature_vector_id"],
                    normalized,
                )
                if build_info["temporal_history"]:
                    build_info["normalized_history"] = [
                        prediction_service.normalize_features(h)
                        for h in build_info["temporal_history"]
                    ]
                else:
                    build_info["normalized_history"] = None

            state.meta["builds_to_predict"] = builds_to_predict
            state.phase = "PREDICTING"

        # Phase: PREDICTING - Run ML prediction
        if state.phase == "PREDICTING":
            builds_to_predict = state.meta["builds_to_predict"]
            results = []

            for build_info in builds_to_predict:
                result = prediction_service.predict(
                    features=build_info["normalized_features"],
                    temporal_history=build_info["normalized_history"],
                    use_prescaled=True,
                )
                results.append(result)

            state.meta["results"] = results
            state.phase = "STORING"

        # Phase: STORING - Store results and update stats
        if state.phase == "STORING":
            builds_to_predict = state.meta["builds_to_predict"]
            results = state.meta["results"]

            succeeded = 0
            failed = 0
            retried_success_count = 0
            new_failure_count = 0

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
                    if not build_info.get("was_previously_failed", False):
                        new_failure_count += 1
                else:
                    updates["prediction_status"] = ExtractionStatus.COMPLETED.value
                    updates["prediction_error"] = None
                    succeeded += 1
                    if build_info.get("was_previously_failed", False):
                        retried_success_count += 1

                model_build_repo.update_one(build_info["id"], updates)
                publish_build_update(
                    repo_config_id, build_info["id"], updates["prediction_status"]
                )

            # Update repo config stats
            if retried_success_count > 0:
                repo_config_repo.decrement_builds_processing_failed(
                    ObjectId(repo_config_id), retried_success_count
                )
            if new_failure_count > 0:
                repo_config_repo.increment_builds_processing_failed(
                    ObjectId(repo_config_id), new_failure_count
                )
            if succeeded > 0:
                repo_config_repo.increment_builds_completed(
                    ObjectId(repo_config_id), succeeded
                )

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

            state.meta["result"] = {
                "status": "completed",
                "processed": len(builds_to_predict),
                "succeeded": succeeded,
                "failed": failed,
            }
            state.phase = "DONE"

        # Phase: DONE - Return result
        return state.meta.get("result", {"status": "completed", "processed": 0})

    return self.run_safe(
        job_id=f"predict:{repo_config_id}:{len(model_build_ids)}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=_cleanup,
        fail_on_unknown=False,  # Unknown errors → retry
    )
