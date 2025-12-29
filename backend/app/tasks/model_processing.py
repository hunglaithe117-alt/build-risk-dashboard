import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

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
from app.tasks.base import PipelineTask
from app.tasks.pipeline.feature_dag._metadata import (
    format_features_for_storage,
)
from app.tasks.shared import extract_features_for_build
from app.tasks.shared.events import publish_build_status as publish_build_update
from app.tasks.shared.events import publish_repo_status as publish_status

logger = logging.getLogger(__name__)


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
    sync_until_existing: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator: Start ingestion for repo, then dispatch processing.

    Flow: start_model_processing -> ingest_model_builds -> dispatch_build_processing
    """
    from app.entities.model_repo_config import ModelImportStatus
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
        {"status": ModelImportStatus.INGESTING.value},
    )
    publish_status(repo_config_id, "ingesting", "Starting import workflow...")

    try:
        ingest_model_builds.delay(
            repo_config_id=repo_config_id,
            ci_provider=ci_provider,
            max_builds=max_builds,
            since_days=since_days,
            only_with_logs=only_with_logs,
            sync_until_existing=sync_until_existing,
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
                "status": ModelImportStatus.FAILED.value,
                "error_message": error_msg,
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

    from celery import chord, group

    from app.entities.enums import ExtractionStatus
    from app.entities.model_repo_config import ModelImportStatus
    from app.repositories.model_import_build import ModelImportBuildRepository
    from app.repositories.model_repo_config import ModelRepoConfigRepository
    from app.repositories.model_training_build import ModelTrainingBuildRepository
    from app.repositories.raw_build_run import RawBuildRunRepository

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    batch_size = settings.PROCESSING_BUILDS_PER_BATCH

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    import_build_repo = ModelImportBuildRepository(self.db)

    if not raw_build_run_ids:
        logger.info(f"{corr_prefix} No builds to process for repo config {repo_config_id}")
        repo_config_repo.update_repository(
            repo_config_id,
            {"status": ModelImportStatus.IMPORTED.value},
        )
        publish_status(repo_config_id, "imported", "No new builds to process")
        return {"repo_config_id": repo_config_id, "dispatched": 0}

    raw_build_runs = raw_build_run_repo.find_by_ids(raw_build_run_ids)
    build_run_map = {str(r.id): r for r in raw_build_runs}

    import_builds = import_build_repo.find_by_raw_build_run_ids(repo_config_id, raw_build_run_ids)
    import_build_map = {str(ib.raw_build_run_id): ib for ib in import_builds}

    run_oids = [ObjectId(rid) for rid in raw_build_run_ids if ObjectId.is_valid(rid)]
    existing_builds_map = model_build_repo.find_existing_by_raw_build_run_ids(
        ObjectId(raw_repo_id), run_oids
    )

    # Step 1: Create ModelTrainingBuild for each raw_build_run
    created_count = 0
    skipped_existing = 0
    model_build_ids = []

    for run_id_str in raw_build_run_ids:
        # O(1) lookup from maps
        raw_build_run = build_run_map.get(run_id_str)
        if not raw_build_run:
            logger.warning(f"{corr_prefix} RawBuildRun {run_id_str} not found, skipping")
            continue

        import_build = import_build_map.get(run_id_str)
        if not import_build:
            logger.warning(f"ModelImportBuild not found for {run_id_str}, skipping")
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
        f"dispatching {len(model_build_ids)} for processing"
    )

    # Update status to PROCESSING - feature extraction begins
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSING.value},
    )
    publish_status(
        repo_config_id,
        "processing",
        f"Scheduling {len(model_build_ids)} builds for processing...",
        stats={
            "builds_fetched": len(raw_build_run_ids),
            "builds_processed": skipped_existing,  # Already processed builds
            "builds_failed": 0,
        },
    )

    # Step 2: Split builds into batches and dispatch batch tasks
    batch_tasks = []
    model_build_id_strs = [str(bid) for bid in model_build_ids]
    total_builds = len(model_build_id_strs)

    # Calculate total batches upfront for correct logging
    import math

    total_batches = math.ceil(total_builds / batch_size) if total_builds > 0 else 0

    for chunk_start in range(0, total_builds, batch_size):
        chunk = model_build_id_strs[chunk_start : chunk_start + batch_size]
        batch_tasks.append(
            process_build_batch.si(
                repo_config_id=repo_config_id,
                model_build_ids=chunk,
                batch_index=len(batch_tasks),
                total_batches=total_batches,
                correlation_id=correlation_id,
            )
        )

    logger.info(
        f"{corr_prefix} Dispatching {total_batches} batch tasks "
        f"({total_builds} builds, batch_size={batch_size})"
    )

    # Dispatch chord: all batches run in parallel, then finalize is called
    chord(
        group(batch_tasks),
        finalize_model_processing.s(
            repo_config_id=repo_config_id,
            created_count=created_count,
            correlation_id=correlation_id,
        ),
    ).apply_async()

    publish_status(
        repo_config_id,
        "processing",
        f"Processing {total_builds} builds in {total_batches} batches...",
    )

    return {
        "repo_config_id": repo_config_id,
        "created": created_count,
        "dispatched": total_builds,
        "batches": total_batches,
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

    # Determine final status
    if failed_count > 0 and success_count == 0:
        final_status = ModelImportStatus.FAILED
    elif failed_count > 0 and success_count > 0:
        final_status = ModelImportStatus.PARTIAL
    else:
        final_status = ModelImportStatus.IMPORTED

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
        # Get IDs of processed builds that need prediction
        builds_for_prediction = model_build_repo.find_builds_needing_prediction(
            ObjectId(repo_config_id)
        )
        if builds_for_prediction:
            build_ids = [str(b.id) for b in builds_for_prediction]
            logger.info(f"{corr_prefix} Dispatching batch prediction for {len(build_ids)} builds")
            predict_builds_batch.delay(build_ids)

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


# Task 3: Process a batch of builds (new batch pattern)
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.process_build_batch",
    queue="processing",
    soft_time_limit=1800,  # 30 min for batch
    time_limit=2100,
)
def process_build_batch(
    self: PipelineTask,
    repo_config_id: str,
    model_build_ids: List[str],
    batch_index: int = 0,
    total_batches: int = 1,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a batch of builds for feature extraction.

    This is the batch version of process_workflow_run, matching the
    enrichment flow pattern (process_enrichment_batch).

    Args:
        repo_config_id: The model_repo_config_id
        model_build_ids: List of ModelTrainingBuild ObjectId strings
        batch_index: Index of this batch (for logging)
        total_batches: Total number of batches (for logging)
        correlation_id: Correlation ID for tracing
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from app.repositories.dataset_template_repository import DatasetTemplateRepository
    from app.services.github.github_client import get_public_github_client
    from app.tasks.pipeline.feature_dag._inputs import GitHubClientInput

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[batch={batch_index + 1}/{total_batches}]"

    model_build_repo = ModelTrainingBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    # Validate repo config exists
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"{log_ctx} Repository Config {repo_config_id} not found")
        return {"status": "error", "error": "Repository Config not found"}

    # Get RawRepository (same for all builds in this batch)
    raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
    if not raw_repo:
        logger.error(f"{log_ctx} RawRepository {repo_config.raw_repo_id} not found")
        return {"status": "error", "error": "RawRepository not found"}

    # Get template features
    template_repo = DatasetTemplateRepository(self.db)
    template = template_repo.find_by_name("TravisTorrent Full")
    feature_names = template.feature_names if template else []

    # Create GitHub client once for the batch
    github_client_input = None
    try:
        client = get_public_github_client()
        github_client_input = GitHubClientInput(client=client, full_name=raw_repo.full_name)
    except Exception as e:
        logger.warning(f"{log_ctx} Failed to create GitHub client: {e}")

    # Process each build in the batch
    processed = 0
    succeeded = 0
    failed = 0
    skipped = 0
    processed_ids = []  # Track which builds we've processed for timeout handling

    try:
        for build_id_str in model_build_ids:
            try:
                result = _process_single_build(
                    db=self.db,
                    model_build_id=build_id_str,
                    repo_config=repo_config,
                    raw_repo=raw_repo,
                    feature_names=feature_names,
                    github_client_input=github_client_input,
                    model_build_repo=model_build_repo,
                    repo_config_repo=repo_config_repo,
                    raw_build_run_repo=raw_build_run_repo,
                    corr_prefix=log_ctx,
                )
                processed += 1
                processed_ids.append(build_id_str)
                status = result.get("status")
                if status in ("completed", "partial"):
                    succeeded += 1
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"{log_ctx} Failed to process build {build_id_str}: {e}")
                failed += 1
                processed += 1
                processed_ids.append(build_id_str)

    except SoftTimeLimitExceeded:
        # Mark remaining (unprocessed) builds as FAILED due to timeout
        unprocessed_ids = [bid for bid in model_build_ids if bid not in processed_ids]
        unprocessed_count = len(unprocessed_ids)

        logger.error(
            f"{log_ctx} TIMEOUT! Processed {len(processed_ids)}/{len(model_build_ids)} "
            f"builds, marking {unprocessed_count} as failed"
        )

        # Mark each unprocessed build as failed
        for build_id in unprocessed_ids:
            model_build_repo.update_one(
                build_id,
                {
                    "extraction_status": ExtractionStatus.FAILED.value,
                    "extraction_error": (
                        "Timeout: batch exceeded time limit before processing this build"
                    ),
                },
            )

        # Update repo config failed count
        if unprocessed_count > 0:
            repo_config_repo.increment_builds_failed(
                ObjectId(repo_config_id),
                count=unprocessed_count,
            )

        # Publish update for real-time UI
        publish_status(
            repo_config_id,
            "processing",
            f"Batch {batch_index + 1} timeout: {len(processed_ids)} processed, "
            f"{unprocessed_count} timed out",
        )

        # Return result instead of re-raising - allows chord callback to aggregate
        # and set PARTIAL status instead of failing entire pipeline
        return {
            "status": "failed",
            "batch_index": batch_index,
            "processed": len(processed_ids),
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed + unprocessed_count,
            "timeout": True,
        }

    logger.info(
        f"{log_ctx} Batch complete: {succeeded}/{processed} succeeded, "
        f"{skipped} skipped, {failed} failed"
    )

    # Send real-time progress update for this batch
    publish_status(
        repo_config_id,
        "processing",
        f"Batch {batch_index + 1}/{total_batches}: {succeeded} builds processed",
        stats={
            "builds_processed": succeeded,
            "builds_failed": failed,
        },
    )

    return {
        "status": "completed" if failed == 0 else "partial",
        "batch_index": batch_index,
        "processed": processed,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
    }


def _process_single_build(
    db,
    model_build_id: str,
    repo_config,
    raw_repo,
    feature_names: List[str],
    github_client_input,
    model_build_repo,
    repo_config_repo,
    raw_build_run_repo,
    corr_prefix: str = "",
) -> Dict[str, Any]:
    """
    Process a single build within a batch.

    Extracted helper to keep process_build_batch clean.
    """
    # Find the ModelTrainingBuild
    model_build = model_build_repo.find_one(
        {
            "_id": ObjectId(model_build_id),
            "extraction_status": ExtractionStatus.PENDING.value,
        }
    )
    if not model_build:
        # Already processed or not found
        return {"status": "skipped", "reason": "not_found_or_processed"}

    # Get the RawBuildRun
    raw_build_run = raw_build_run_repo.find_by_id(model_build.raw_build_run_id)
    if not raw_build_run:
        model_build_repo.update_one(
            model_build_id,
            {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": "RawBuildRun not found",
            },
        )
        return {"status": "failed", "error": "RawBuildRun not found"}

    build_id = str(model_build.id)

    # Extract features using shared helper
    from app.entities.feature_audit_log import AuditLogCategory

    result = extract_features_for_build(
        db=db,
        raw_repo=raw_repo,
        feature_config=repo_config.feature_configs,
        raw_build_run=raw_build_run,
        selected_features=feature_names,
        github_client=github_client_input,
        output_build_id=str(model_build.id),
        category=AuditLogCategory.MODEL_TRAINING,
    )

    # Update build with results
    updates = {
        "features": format_features_for_storage(result.get("features", {})),
        "feature_count": result.get("feature_count", 0),
    }

    if result["status"] == "completed":
        updates["extraction_status"] = ExtractionStatus.COMPLETED.value
    elif result["status"] == "partial":
        updates["extraction_status"] = ExtractionStatus.PARTIAL.value
    else:
        updates["extraction_status"] = ExtractionStatus.FAILED.value

    if result.get("errors"):
        updates["extraction_error"] = "; ".join(result["errors"])
    elif result.get("warnings"):
        updates["extraction_error"] = "Warning: " + "; ".join(result["warnings"])

    if result.get("is_missing_commit"):
        updates["is_missing_commit"] = True
    if result.get("missing_resources"):
        updates["missing_resources"] = result["missing_resources"]
    if result.get("skipped_features"):
        updates["skipped_features"] = result["skipped_features"]

    model_build_repo.update_one(build_id, updates)

    # Publish build status update for real-time UI
    publish_build_update(str(repo_config.id), build_id, updates["extraction_status"])

    # Update repo config stats: only track failed builds at extraction time
    # builds_completed is incremented after prediction completes
    if updates["extraction_status"] == ExtractionStatus.FAILED.value:
        repo_config_repo.increment_builds_failed(ObjectId(repo_config.id))

    if result.get("missing_resources"):
        try:
            import_build_repo = ModelImportBuildRepository(db)
            import_build = import_build_repo.find_one(
                {"raw_build_run_id": ObjectId(model_build.raw_build_run_id)}
            )
            if import_build:
                import_build_repo.update_one(
                    str(import_build.id),
                    {
                        "status": ModelImportBuildStatus.FAILED.value,
                        "ingestion_error": f"Missing resources: {result['missing_resources']}",
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to update ModelImportBuild status: {e}")

    return {
        "status": result["status"],
        "build_id": build_id,
        "feature_count": result.get("feature_count", 0),
    }


# Task 4: Process a single build (legacy, kept for backward compatibility)
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

    # Notify clients that processing started
    publish_build_update(repo_config_id, build_id, "in_progress")

    try:
        # Fetch RawRepository for RepoInput
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
        if not raw_repo:
            logger.error(f"{corr_prefix} RawRepository {repo_config.raw_repo_id} not found")
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
            logger.warning(f"{corr_prefix} Failed to create GitHub client: {e}")

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
                "builds_fetched": updated_config.builds_fetched,
                "builds_completed": updated_config.builds_completed,
                "builds_failed": updated_config.builds_failed,
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
    name="app.tasks.processing.reprocess_failed_builds",
    queue="processing",
    soft_time_limit=300,
    time_limit=360,
)
def reprocess_failed_builds(self: PipelineTask, repo_config_id: str) -> Dict[str, Any]:
    """
    Reprocess only FAILED builds for a repository.

    Uses chord with finalize callback to ensure status is updated properly.

    This is useful when:
    - Some builds failed due to transient errors (network, rate limits)
    - Feature extractors have been fixed
    - You want to retry only the failed builds, not all builds
    """
    from celery import chord, group

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
        f"Retrying {len(build_ids)} failed builds...",
        stats={"builds_failed": len(failed_builds)},
    )

    # Build processing tasks
    processing_tasks = [
        process_workflow_run.si(
            repo_config_id=repo_config_id,
            model_build_id=build_id,
            is_reprocess=True,
            correlation_id=correlation_id,
        )
        for build_id in build_ids
    ]

    # Use chord with finalize callback to properly update status
    workflow = chord(
        group(processing_tasks),
        finalize_model_processing.s(
            repo_config_id=repo_config_id,
            created_count=len(build_ids),
            correlation_id=correlation_id,
        ),
    )
    workflow.apply_async()

    logger.info(f"Dispatched chord with {len(build_ids)} reprocess tasks for {repo_config_id}")

    return {
        "status": "queued",
        "builds_queued": len(build_ids),
        "total_failed": len(failed_builds),
        "correlation_id": correlation_id,
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
    Uses batch prediction endpoint if available.
    After prediction, increments builds_completed count on repo config.
    """
    from app.services.prediction_service import PredictionService

    if not model_build_ids:
        return {"status": "completed", "processed": 0}

    model_build_repo = ModelTrainingBuildRepository(self.db)
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
        if not model_build.features:
            model_build_repo.update_one(
                build_id,
                {"prediction_error": "No features available"},
            )
            continue

        builds_to_predict.append(
            {
                "id": build_id,
                "features": model_build.features,
                "repo_config_id": model_build.model_repo_config_id,
            }
        )
        repo_config_ids.add(model_build.model_repo_config_id)

    if not builds_to_predict:
        return {"status": "completed", "processed": 0, "skipped": len(model_build_ids)}

    # Batch predict
    feature_list = [b["features"] for b in builds_to_predict]
    results = prediction_service.predict_batch(feature_list)

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
