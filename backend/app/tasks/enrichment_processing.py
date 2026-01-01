"""
Version Enrichment Processing Tasks - Phase 2: Feature Extraction.

This module handles the processing phase of dataset version enrichment:
1. start_enrichment_processing - Trigger processing after ingestion
2. dispatch_scans_and_processing - Dispatch scans + batches
3. dispatch_enrichment_batches - Dispatch batch processing
4. process_single_enrichment - Extract features for a batch of builds
5. finalize_enrichment - Mark version as completed
6. reprocess_failed_enrichment_builds - Retry failed builds
7. process_version_export_job - Export version data

Phase 1 (ingestion) is in enrichment_ingestion.py.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from bson import ObjectId
from celery import chain
from celery.canvas import group

from app.celery_app import celery_app
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.dataset_version import VersionStatus
from app.entities.enums import ExtractionStatus
from app.entities.feature_audit_log import AuditLogCategory
from app.paths import EXPORTS_DIR
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_import_build import DatasetImportBuildRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import EnrichmentTask, PipelineTask
from app.tasks.shared import extract_features_for_build
from app.tasks.shared.events import publish_enrichment_update
from app.tasks.shared.processing_tracker import ProcessingTracker

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.start_enrichment_processing",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def start_enrichment_processing(
    self: PipelineTask,
    version_id: str,
) -> Dict[str, Any]:
    """
    Phase 2: Start processing phase (manually triggered by user).

    Validates that ingestion is complete before starting feature extraction.
    Only proceeds if status is INGESTED.
    """
    correlation_id = TracingContext.get_correlation_id() or str(uuid.uuid4())
    corr_prefix = f"[corr={correlation_id[:8]}]"

    import_build_repo = DatasetImportBuildRepository(self.db)
    version_repo = DatasetVersionRepository(self.db)

    # Validate status
    version = version_repo.find_by_id(version_id)
    if not version:
        logger.error(f"{corr_prefix} Version {version_id} not found")
        return {"status": "error", "message": "Version not found"}

    valid_statuses = [
        VersionStatus.INGESTED.value,
    ]
    if version.status not in valid_statuses:
        msg = f"Cannot start processing: status is {version.status}. " f"Expected: {valid_statuses}"
        logger.warning(f"{corr_prefix} {msg}")
        return {"status": "error", "message": msg}

    # Query INGESTED builds
    ingested_builds = import_build_repo.find_ingested_builds(version_id)

    if not ingested_builds:
        logger.info(f"{corr_prefix} No ingested builds for {version_id}")
        return {"status": "completed", "builds": 0, "message": "No builds to process"}

    # Update status to PROCESSING
    version_repo.update_one(version_id, {"status": VersionStatus.PROCESSING.value})

    # Dispatch scans (if configured) and processing batches
    dispatch_scans_and_processing.delay(version_id, correlation_id=correlation_id)

    logger.info(f"{corr_prefix} Dispatched processing for {len(ingested_builds)} builds")

    publish_enrichment_update(
        version_id=version_id,
        status=VersionStatus.PROCESSING.value,
    )

    return {"status": "dispatched", "builds": len(ingested_builds)}


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.dispatch_scans_and_processing",
    queue="processing",
    soft_time_limit=30,
    time_limit=60,
)
def dispatch_scans_and_processing(
    self: PipelineTask,
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Dispatch scans (async, fire & forget) and processing after ingestion completes.

    Scans run independently without blocking feature extraction.
    Scan results are backfilled to DatasetEnrichmentBuild.features later.
    """
    # Get correlation_id for propagation to child tasks
    correlation_id = correlation_id or TracingContext.get_correlation_id() or ""
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        return {"status": "error", "error": "Version not found"}

    has_sonar = bool(version.scan_metrics.get("sonarqube"))
    has_trivy = bool(version.scan_metrics.get("trivy"))

    # Dispatch scans (async, fire & forget - doesn't block processing)
    if has_sonar or has_trivy:
        logger.info(
            f"{corr_prefix}[dispatch_scans_and_processing] Dispatching scans: "
            f"sonar={has_sonar}, trivy={has_trivy}"
        )
        # Import here to avoid circular import
        from app.tasks.enrichment_ingestion import dispatch_version_scans

        dispatch_version_scans.delay(version_id, correlation_id=correlation_id)

    # Dispatch processing immediately (doesn't wait for scans)
    dispatch_enrichment_batches.delay(version_id, correlation_id=correlation_id)

    logger.info(
        f"{corr_prefix}[dispatch_scans_and_processing] Processing dispatched for {version_id}"
    )

    return {
        "status": "dispatched",
        "scans_dispatched": has_sonar or has_trivy,
        "processing_dispatched": True,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.handle_enrichment_processing_chain_error",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def handle_enrichment_processing_chain_error(
    self: PipelineTask,
    request,
    exc,
    traceback,
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Error callback for processing chain failure.

    When processing chain fails (feature extraction error, worker crash, etc.):
    1. Mark all IN_PROGRESS enrichment builds as FAILED with error
    2. Update version status to PROCESSED or FAILED
    3. Publish update for UI

    This ensures temporal feature integrity - if one build fails,
    subsequent builds cannot have correct temporal features.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    error_msg = str(exc) if exc else "Unknown chain error"

    logger.error(
        f"{corr_prefix}[handle_enrichment_processing_chain_error] "
        f"Processing chain failed for version {version_id}: {error_msg}"
    )

    version_repo = DatasetVersionRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)

    # Mark all IN_PROGRESS builds as FAILED
    in_progress_count = enrichment_build_repo.mark_in_progress_as_failed(
        version_id,
        error_message=f"Chain stopped: {error_msg}",
    )

    # Count completed vs failed for status determination
    completed_count = enrichment_build_repo.count_by_status(
        ObjectId(version_id), ExtractionStatus.COMPLETED.value
    )
    failed_count = enrichment_build_repo.count_by_status(
        ObjectId(version_id), ExtractionStatus.FAILED.value
    )

    # Determine final status - always PROCESSED if any succeeded, else FAILED
    if completed_count > 0:
        final_status = VersionStatus.PROCESSED.value
    else:
        final_status = VersionStatus.FAILED.value

    version_repo.mark_status(version_id, final_status)

    # Publish update for UI
    publish_enrichment_update(
        version_id=version_id,
        status=final_status,
        error=f"Processing chain failed: {error_msg}",
    )

    logger.info(
        f"{corr_prefix}[handle_enrichment_processing_chain_error] "
        f"Marked {in_progress_count} builds as FAILED, status={final_status}"
    )

    return {
        "status": final_status,
        "in_progress_marked_failed": in_progress_count,
        "completed": completed_count,
        "failed": failed_count,
        "error": error_msg,
    }


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.dispatch_enrichment_batches",
    queue="processing",
    soft_time_limit=120,
    time_limit=180,
)
def dispatch_enrichment_batches(
    self: PipelineTask,
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Dispatch enrichment processing for INGESTED builds.

    Flow (matching model pipeline):
    1. Get INGESTED DatasetImportBuild records
    2. Create DatasetEnrichmentBuild for each (if not exists)
    3. Dispatch sequential chain for temporal feature support
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    import_build_repo = DatasetImportBuildRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)

    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        raise ValueError(f"Version {version_id} not found")

    # Step 1: Get INGESTED import builds (sorted by build creation time)
    ingested_imports = import_build_repo.find_ingested_builds(version_id)

    if not ingested_imports:
        logger.info(f"{corr_prefix} No ingested builds for {version_id}")
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No ingested builds to process"}

    # Build lookup map for raw_build_run data
    raw_build_run_ids = [
        ObjectId(ib.raw_build_run_id)
        if isinstance(ib.raw_build_run_id, str)
        else ib.raw_build_run_id
        for ib in ingested_imports
    ]
    # Type ignore: method accepts List[str | ObjectId]
    raw_build_runs = raw_build_run_repo.find_by_ids(raw_build_run_ids)  # type: ignore
    build_run_map = {str(r.id): r for r in raw_build_runs}

    # Sort by build creation time (oldest first) for temporal features
    ingested_imports.sort(
        key=lambda ib: (build_run_map.get(str(ib.raw_build_run_id), ib).created_at or ib.created_at)
    )

    # Step 2: Create DatasetEnrichmentBuild for each (if not exists)
    created_count = 0
    skipped_existing = 0
    enrichment_build_ids = []

    for import_build in ingested_imports:
        # Check if already exists
        existing = enrichment_build_repo.find_by_import_build(str(import_build.id))
        if existing and existing.extraction_status != ExtractionStatus.PENDING.value:
            skipped_existing += 1
            continue

        # Create or get DatasetEnrichmentBuild
        enrichment_build = enrichment_build_repo.upsert_for_import_build(
            dataset_version_id=version_id,
            dataset_id=str(dataset_version.dataset_id),
            dataset_build_id=str(import_build.dataset_build_id),
            dataset_import_build_id=str(import_build.id),
            raw_repo_id=str(import_build.raw_repo_id),
            raw_build_run_id=str(import_build.raw_build_run_id),
        )
        enrichment_build_ids.append(str(enrichment_build.id))
        created_count += 1

    logger.info(
        f"{corr_prefix} Created {created_count} enrichment builds, "
        f"skipped {skipped_existing} already processed"
    )

    if not enrichment_build_ids:
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No pending builds to process"}

    # Step 3: Dispatch sequential processing (oldest → newest for temporal features)
    total_builds = len(enrichment_build_ids)

    # Initialize ProcessingTracker for this enrichment batch
    tracker = ProcessingTracker(self.redis, version_id, correlation_id)
    tracker.initialize(total_builds)

    sequential_tasks = [
        process_single_enrichment.si(
            version_id=version_id,
            enrichment_build_id=build_id,
            selected_features=dataset_version.selected_features,
            correlation_id=correlation_id,
        )
        for build_id in enrichment_build_ids
    ]

    logger.info(f"{corr_prefix} Dispatching {total_builds} builds for sequential processing")

    # Chain: B1 → B2 → B3 → ... → finalize
    # Each build processes after the previous one completes
    workflow = chain(
        *sequential_tasks,
        finalize_enrichment.si(
            version_id=version_id,
            created_count=created_count,
            correlation_id=correlation_id,
        ),
    )

    # Add error callback to handle unexpected chain failures (worker crash, OOM, etc.)
    error_callback = handle_enrichment_processing_chain_error.s(
        version_id=version_id,
        correlation_id=correlation_id,
    )
    workflow.on_error(error_callback).apply_async()

    publish_enrichment_update(
        version_id=version_id,
        status="processing",
        builds_total=total_builds,
    )

    return {
        "status": "dispatched",
        "total_builds": total_builds,
        "created": created_count,
        "skipped": skipped_existing,
    }


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.process_single_enrichment",
    queue="processing",
    soft_time_limit=300,
    time_limit=600,
)
def process_single_enrichment(
    self: PipelineTask,
    version_id: str,
    enrichment_build_id: str,
    selected_features: List[str],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a single enrichment build for feature extraction.

    This is the sequential version matching model pipeline's process_workflow_run.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    # Get enrichment build
    enrichment_build = enrichment_build_repo.find_by_id(enrichment_build_id)
    if not enrichment_build:
        logger.error(f"{corr_prefix} EnrichmentBuild {enrichment_build_id} not found")
        return {"status": "error", "error": "EnrichmentBuild not found"}

    # Skip if already processed
    if enrichment_build.extraction_status != ExtractionStatus.PENDING.value:
        return {"status": "skipped", "reason": "already_processed"}

    # Get raw build run
    raw_build_run = raw_build_run_repo.find_by_id(enrichment_build.raw_build_run_id)
    if not raw_build_run:
        enrichment_build_repo.update_one(
            enrichment_build_id,
            {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": "RawBuildRun not found",
            },
        )
        return {"status": "failed", "error": "RawBuildRun not found"}

    # Get raw repo
    raw_repo = raw_repo_repo.find_by_id(raw_build_run.raw_repo_id)
    if not raw_repo:
        enrichment_build_repo.update_one(
            enrichment_build_id,
            {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": "RawRepository not found",
            },
        )
        return {"status": "failed", "error": "RawRepository not found"}

    # Get version for feature config
    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        return {"status": "error", "error": "Version not found"}

    # Extract features using shared helper
    result = extract_features_for_build(
        db=self.db,
        raw_repo=raw_repo,
        feature_config=dataset_version.feature_configs,
        raw_build_run=raw_build_run,
        selected_features=selected_features,
        output_build_id=enrichment_build_id,
        category=AuditLogCategory.DATASET_ENRICHMENT,
    )

    # Update enrichment build with results
    updates = {
        "feature_vector_id": result.get("feature_vector_id"),
    }

    if result["status"] == "completed":
        updates["extraction_status"] = ExtractionStatus.COMPLETED.value
    elif result["status"] == "partial":
        updates["extraction_status"] = ExtractionStatus.PARTIAL.value
    else:
        updates["extraction_status"] = ExtractionStatus.FAILED.value

    if result.get("errors"):
        updates["extraction_error"] = "; ".join(result["errors"])

    enrichment_build_repo.update_one(enrichment_build_id, updates)

    # Update version progress
    version_repo.increment_builds_processed(version_id)

    # Track result in Redis for finalize aggregation (matching model pipeline)
    if correlation_id:
        tracker = ProcessingTracker(self.redis, version_id, correlation_id)
        if result["status"] in ("completed", "partial"):
            tracker.record_success(enrichment_build_id)
        else:
            tracker.record_failure(enrichment_build_id)

    logger.debug(
        f"{corr_prefix} Processed enrichment build {enrichment_build_id}: "
        f"status={result['status']}"
    )

    return {
        "status": result["status"],
        "build_id": enrichment_build_id,
        "feature_count": result.get("feature_count", 0),
    }


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.reprocess_failed_enrichment_builds",
    queue="processing",
    soft_time_limit=300,
    time_limit=360,
)
def reprocess_failed_enrichment_builds(
    self: PipelineTask,
    version_id: str,
) -> Dict[str, Any]:
    """
    Reprocess only FAILED enrichment builds for a version.

    Uses sequential chain to ensure temporal features work correctly.

    This is useful when:
    - Some builds failed due to transient errors (network, rate limits)
    - Feature extractors have been fixed
    - You want to retry only the failed builds, not all builds
    """
    correlation_id = str(uuid.uuid4())
    TracingContext.set(
        correlation_id=correlation_id,
        version_id=version_id,
        pipeline_type="reprocess_failed",
    )

    version_repo = DatasetVersionRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)

    # Validate version exists
    version = version_repo.find_by_id(version_id)
    if not version:
        logger.error(f"Version {version_id} not found")
        return {"status": "error", "message": "Version not found"}

    # Find only FAILED enrichment builds
    failed_builds = enrichment_build_repo.find_many(
        {
            "dataset_version_id": ObjectId(version_id),
            "extraction_status": ExtractionStatus.FAILED.value,
        }
    )

    if not failed_builds:
        logger.info(f"No failed enrichment builds for version {version_id}")
        return {
            "status": "completed",
            "builds_queued": 0,
            "message": "No failed builds to reprocess",
        }

    # Reset failed builds to PENDING
    build_ids = []
    for build in failed_builds:
        try:
            enrichment_build_repo.update_one(
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
        return {"status": "error", "message": "Failed to reset builds"}

    # Update version status
    version_repo.update_one(version_id, {"status": VersionStatus.PROCESSING.value})

    publish_enrichment_update(
        version_id=version_id,
        status="processing",
    )

    # Build sequential processing tasks (oldest → newest)
    processing_tasks = [
        process_single_enrichment.si(
            version_id=version_id,
            enrichment_build_id=build_id,
            selected_features=version.selected_features,
            correlation_id=correlation_id,
        )
        for build_id in build_ids
    ]

    # Sequential chain: B1 → B2 → B3 → ... → finalize
    workflow = chain(
        *processing_tasks,
        finalize_enrichment.si(
            version_id=version_id,
            created_count=len(build_ids),
            correlation_id=correlation_id,
        ),
    )
    workflow.apply_async()

    logger.info(f"Dispatched reprocess chain with {len(build_ids)} failed builds")

    return {
        "status": "queued",
        "builds_queued": len(build_ids),
        "total_failed": len(failed_builds),
        "correlation_id": correlation_id,
    }


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.finalize_enrichment",
    queue="processing",
    soft_time_limit=30,
    time_limit=60,
)
def finalize_enrichment(
    self: PipelineTask,
    version_id: str,
    created_count: int = 0,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Finalize enrichment after all sequential builds processed.

    Called at end of chain: B1 → B2 → ... → finalize_enrichment
    Uses ProcessingTracker for real-time results (matching model pipeline).
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(f"{corr_prefix} Finalizing enrichment for version {version_id}")

    version_repo = DatasetVersionRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)

    # Get results from Redis tracker (matching model pipeline pattern)
    tracker = ProcessingTracker(self.redis, version_id, correlation_id)
    tracker_results = tracker.get_results()

    tracker_success = tracker_results["success_count"]
    tracker_failed = tracker_results["failed_count"]
    tracker_skipped = tracker_results["skipped_count"]

    logger.info(
        f"{corr_prefix} Processing results from tracker: "
        f"success={tracker_success}, failed={tracker_failed}, skipped={tracker_skipped}"
    )

    # Also get aggregated stats from DB for verification
    stats = enrichment_build_repo.aggregate_stats_by_version(version_id)
    completed = stats.get("completed", 0)
    partial = stats.get("partial", 0)
    failed = stats.get("failed", 0)
    total = completed + partial + failed

    # Determine final status
    # Always PROCESSED unless all builds failed
    if failed > 0 and completed == 0:
        final_status = VersionStatus.FAILED
    else:
        final_status = VersionStatus.PROCESSED

    # Update version
    version_repo.update_one(
        version_id,
        {
            "status": final_status.value,
            "builds_processed": completed + partial,
            "builds_processing_failed": failed,
        },
    )

    # Publish completion via WebSocket
    publish_enrichment_update(
        version_id=version_id,
        status=final_status.value,
        builds_processed=completed + partial,
        builds_total=total,
    )

    # Auto-trigger quality evaluation after successful enrichment
    dataset_version = version_repo.find_by_id(version_id)
    if dataset_version and final_status == VersionStatus.PROCESSED:
        try:
            from app.services.data_quality_service import DataQualityService

            quality_service = DataQualityService(self.db)
            quality_report = quality_service.evaluate_version(
                dataset_id=str(dataset_version.dataset_id),
                version_id=version_id,
            )
            logger.info(
                f"{corr_prefix} Auto quality evaluation completed: "
                f"quality_score={quality_report.quality_score:.2f}"
            )
        except Exception as e:
            logger.warning(f"{corr_prefix} Auto quality evaluation failed: {e}")

    logger.info(
        f"{corr_prefix} Version enrichment completed: {version_id}, "
        f"{completed + partial}/{total} rows enriched, {failed} failed"
    )

    # Cleanup tracker after finalization (matching model pipeline)
    tracker.cleanup()

    return {
        "status": final_status.value,
        "version_id": version_id,
        "builds_processed": completed + partial,
        "builds_processing_failed": failed,
        "builds_total": total,
        "tracker_stats": {
            "success": tracker_success,
            "failed": tracker_failed,
            "skipped": tracker_skipped,
        },
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.process_version_export_job",
    queue="processing",
    soft_time_limit=600,
    time_limit=900,
)
def process_version_export_job(self: PipelineTask, job_id: str) -> Dict[str, Any]:
    """
    Process async export job for dataset version.

    Writes CSV/JSON file to disk with progress updates.
    """
    from app.repositories.export_job import ExportJobRepository
    from app.utils.export_utils import format_feature_row, write_csv_file, write_json_file

    job_repo = ExportJobRepository(self.db)
    enrichment_repo = DatasetEnrichmentBuildRepository(self.db)

    job = job_repo.find_by_id(job_id)
    if not job:
        logger.error(f"Export job {job_id} not found")
        return {"status": "error", "message": "Job not found"}

    # Validate job has required fields for version export
    if not job.dataset_id or not job.version_id:
        logger.error(f"Export job {job_id} missing dataset_id or version_id")
        job_repo.update_status(job_id, "failed", error_message="Missing dataset_id or version_id")
        return {"status": "error", "message": "Missing dataset_id or version_id"}

    # Mark as processing
    job_repo.update_status(job_id, "processing")

    try:
        # Get data cursor - convert ObjectId to ObjectId (they're already ObjectId in entity)
        dataset_oid = (
            ObjectId(job.dataset_id) if isinstance(job.dataset_id, str) else job.dataset_id
        )
        version_oid = (
            ObjectId(job.version_id) if isinstance(job.version_id, str) else job.version_id
        )

        cursor = enrichment_repo.get_enriched_for_export(
            dataset_id=dataset_oid,
            version_id=version_oid,
        )

        # Get all feature keys for CSV headers
        all_feature_keys = enrichment_repo.get_all_feature_keys(
            dataset_id=dataset_oid,
            version_id=version_oid,
        )

        # Prepare output path - use centralized EXPORTS_DIR
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"version_{job.version_id}_{timestamp}.{job.format}"
        from pathlib import Path

        file_path = Path(EXPORTS_DIR / filename)

        # Progress callback
        def update_progress(processed: int) -> None:
            if processed % 500 == 0:  # Update every 500 rows
                job_repo.update_progress(job_id, processed)

        # Write file
        if job.format == "csv":
            write_csv_file(
                file_path=file_path,
                cursor=cursor,
                format_row_fn=format_feature_row,
                features=list(job.features) if job.features else None,
                all_feature_keys=all_feature_keys,
                progress_callback=update_progress,
            )
        else:
            write_json_file(
                file_path=file_path,
                cursor=cursor,
                format_row_fn=format_feature_row,
                features=list(job.features) if job.features else None,
                progress_callback=update_progress,
            )

        # Get file size
        file_size = file_path.stat().st_size

        # Mark completed
        job_repo.update_status(
            job_id,
            "completed",
            file_path=file_path,
            file_size=file_size,
            processed_rows=job.total_rows,
            completed_at=datetime.now(timezone.utc),
        )

        logger.info(f"Export job {job_id} completed: {file_path} ({file_size} bytes)")
        return {"status": "completed", "file_path": file_path}

    except Exception as exc:
        logger.error(f"Export job {job_id} failed: {exc}")
        job_repo.update_status(job_id, "failed", error_message=str(exc))
        raise


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.dispatch_version_scans",
    queue="processing",
    soft_time_limit=300,
    time_limit=600,
)
def dispatch_version_scans(
    self: PipelineTask,
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Dispatch scans for all unique commits in version's validated builds.

    Uses chunked processing to handle:
    1. Paginate through builds using cursor pagination
    2. Batch query RawBuildRuns and RawRepositories
    3. Dispatch scan tasks in configurable batches

    Config settings:
        SCAN_BUILDS_PER_QUERY: Builds fetched per paginated query (default: 1000)
        SCAN_COMMITS_PER_BATCH: Commits dispatched per batch (default: 100)
        SCAN_BATCH_DELAY_SECONDS: Delay between batch dispatches (default: 0.5)
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        return {"status": "error", "error": "Version not found"}

    has_sonar = bool(version.scan_metrics.get("sonarqube"))
    has_trivy = bool(version.scan_metrics.get("trivy"))

    if not has_sonar and not has_trivy:
        return {"status": "skipped", "reason": "No scan metrics selected"}

    # Track unique commits to scan (avoid duplicates across pages)
    commits_to_scan: Dict[tuple, Dict[str, Any]] = {}  # {(repo_id, commit_sha): commit_info}
    repo_cache: Dict[str, Any] = {}  # Cache RawRepository lookups

    # Config
    builds_per_query = settings.SCAN_BUILDS_PER_QUERY
    commits_per_batch = settings.SCAN_COMMITS_PER_BATCH
    batch_delay = settings.SCAN_BATCH_DELAY_SECONDS

    total_builds_processed = 0
    total_batches_dispatched = 0

    logger.info(
        f"{corr_prefix} Starting chunked scan dispatch for version {version_id[:8]} "
        f"(builds_per_query={builds_per_query}, commits_per_batch={commits_per_batch})"
    )

    # Import scan helper here
    from app.tasks.enrichment_scan_helpers import dispatch_scan_for_commit

    # Iterate through builds using cursor pagination
    for build_batch in dataset_build_repo.iterate_builds_with_run_ids_paginated(
        dataset_id=str(version.dataset_id),
        batch_size=builds_per_query,
    ):
        total_builds_processed += len(build_batch)

        # Collect workflow_run_ids from this batch (these are RawBuildRun ObjectIds)
        workflow_run_ids = [b.raw_run_id for b in build_batch if b.raw_run_id]
        if not workflow_run_ids:
            continue

        # Batch query RawBuildRuns for this page
        raw_build_runs = raw_build_run_repo.find_by_ids(workflow_run_ids)
        build_run_map = {str(r.id): r for r in raw_build_runs}

        # Collect unique repo IDs needed for this batch
        repo_ids_needed = set()
        for build in build_batch:
            if not build.raw_run_id:
                continue
            raw_build_run = build_run_map.get(str(build.raw_run_id))
            if raw_build_run:
                repo_id = str(raw_build_run.raw_repo_id)
                if repo_id not in repo_cache:
                    repo_ids_needed.add(repo_id)

        # Batch query RawRepositories (only ones not in cache)
        if repo_ids_needed:
            raw_repos = raw_repo_repo.find_by_ids(list(repo_ids_needed))
            for repo in raw_repos:
                repo_cache[str(repo.id)] = repo

        # Process builds and collect unique commits
        for build in build_batch:
            if not build.raw_run_id:
                continue
            raw_build_run = build_run_map.get(str(build.raw_run_id))
            if not raw_build_run:
                continue

            repo_id = str(raw_build_run.raw_repo_id)
            raw_repo = repo_cache.get(repo_id)
            if not raw_repo:
                continue

            key = (repo_id, raw_build_run.commit_sha)
            if key not in commits_to_scan:
                commits_to_scan[key] = {
                    "raw_repo_id": repo_id,
                    "commit_sha": raw_build_run.commit_sha,
                    "github_repo_id": raw_repo.github_repo_id,
                    "repo_full_name": raw_repo.full_name,
                }

        # Check if we should dispatch a batch
        if len(commits_to_scan) >= commits_per_batch:
            batch_count = _dispatch_scan_batch(
                version_id=version_id,
                commits=list(commits_to_scan.values())[:commits_per_batch],
                dispatch_scan_for_commit=dispatch_scan_for_commit,
                corr_prefix=corr_prefix,
            )
            total_batches_dispatched += 1

            # Remove dispatched commits
            dispatched_keys = list(commits_to_scan.keys())[:commits_per_batch]
            for k in dispatched_keys:
                del commits_to_scan[k]

            # Rate limiting between batches
            if batch_delay > 0:
                time.sleep(batch_delay)

            logger.info(
                f"{corr_prefix} Dispatched batch {total_batches_dispatched}: "
                f"{batch_count} scan tasks "
                f"(processed {total_builds_processed} builds so far)"
            )

    # Dispatch remaining commits
    if commits_to_scan:
        batch_count = _dispatch_scan_batch(
            version_id=version_id,
            commits=list(commits_to_scan.values()),
            dispatch_scan_for_commit=dispatch_scan_for_commit,
            corr_prefix=corr_prefix,
        )
        total_batches_dispatched += 1
        logger.info(f"{corr_prefix} Dispatched final batch: {batch_count} scan tasks")

    logger.info(
        f"{corr_prefix} Scan dispatch complete: "
        f"{total_builds_processed} builds processed, "
        f"{total_batches_dispatched} batches dispatched"
    )

    return {
        "status": "dispatched",
        "builds_processed": total_builds_processed,
        "batches_dispatched": total_batches_dispatched,
        "has_sonar": has_sonar,
        "has_trivy": has_trivy,
    }


def _dispatch_scan_batch(
    version_id: str,
    commits: List[Dict[str, Any]],
    dispatch_scan_for_commit,
    corr_prefix: str,
) -> int:
    """Helper to dispatch a batch of scan tasks."""
    scan_tasks = []
    for commit_info in commits:
        scan_tasks.append(
            dispatch_scan_for_commit.si(
                version_id=version_id,
                raw_repo_id=commit_info["raw_repo_id"],
                github_repo_id=commit_info["github_repo_id"],
                commit_sha=commit_info["commit_sha"],
                repo_full_name=commit_info["repo_full_name"],
            )
        )

    if scan_tasks:
        group(scan_tasks).apply_async()

    return len(scan_tasks)
