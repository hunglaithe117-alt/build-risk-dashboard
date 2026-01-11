"""
Training Pipeline - Processing Tasks (Phase 2)

This module handles the processing phase of training scenario (user-triggered):
1. start_scenario_processing - Entry point: User triggers after reviewing ingestion
2. dispatch_scans_and_processing - Dispatch scans (async) + feature extraction
3. dispatch_enrichment_batches - Create EnrichmentBuild + dispatch sequential chain
4. process_single_enrichment - Process single build for feature extraction
5. finalize_scenario_processing - Finalize after all builds processed
6. reprocess_failed_builds - Retry FAILED enrichment builds
7. split_scenario_dataset - Apply splitting strategy and export files

Scan dispatch tasks:
8. dispatch_scenario_scans - Dispatch scans for unique commits
9. process_scan_batch - Process scan batch
10. finalize_scan_dispatch - Finalize scan dispatch
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from bson import ObjectId
from celery import chain

from app import paths
from app.celery_app import celery_app
from app.entities.enums import ExtractionStatus
from app.entities.training_enrichment_build import TrainingEnrichmentBuild
from app.entities.training_ingestion_build import (
    IngestionStatus,
    TrainingIngestionBuild,
)
from app.entities.training_scenario import ScenarioStatus, TrainingScenario
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.repositories.training_dataset_split import TrainingDatasetSplitRepository
from app.repositories.training_enrichment_build import TrainingEnrichmentBuildRepository
from app.repositories.training_ingestion_build import TrainingIngestionBuildRepository
from app.repositories.training_scenario import TrainingScenarioRepository
from app.tasks.base import PipelineTask, SafeTask, TaskState
from app.tasks.shared.events import publish_scenario_update

logger = logging.getLogger(__name__)


# ============================================================================
# PHASE 2: PROCESSING (User-Triggered)
# ============================================================================


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.start_scenario_processing",
    queue="scenario_processing",
    soft_time_limit=60,
    time_limit=120,
)
def start_scenario_processing(
    self: PipelineTask,
    scenario_id: str,
) -> Dict[str, Any]:
    """
    Phase 2: Start processing phase (manually triggered by user).

    Validates that ingestion is complete before starting feature extraction.
    Only proceeds if status is INGESTED.
    """
    import uuid

    correlation_id = str(uuid.uuid4())
    logger.info(f"[start_scenario_processing] Starting for scenario {scenario_id}")

    scenario_repo = TrainingScenarioRepository(self.db)

    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "error": "Scenario not found"}

    # Validate status
    if scenario.status != ScenarioStatus.INGESTED.value:
        return {
            "status": "error",
            "error": f"Cannot start processing: status is {scenario.status}, expected INGESTED",
        }

    # Update status to PROCESSING
    scenario_repo.update_one(
        scenario_id,
        {
            "status": ScenarioStatus.PROCESSING.value,
            "processing_started_at": datetime.utcnow(),
            "current_task_id": self.request.id,
        },
    )

    publish_scenario_update(
        scenario_id=scenario_id,
        status=ScenarioStatus.PROCESSING.value,
        current_phase="Starting feature extraction...",
    )

    # Dispatch scans and processing
    dispatch_scans_and_processing.delay(
        scenario_id=scenario_id,
        correlation_id=correlation_id,
    )

    return {
        "status": "dispatched",
        "scenario_id": scenario_id,
        "correlation_id": correlation_id,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.dispatch_scans_and_processing",
    queue="scenario_processing",
    soft_time_limit=120,
    time_limit=180,
)
def dispatch_scans_and_processing(
    self: PipelineTask,
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Dispatch scans (async, fire & forget) and processing after ingestion completes.

    Scans run independently without blocking feature extraction.
    Scan results are backfilled to FeatureVector.scan_metrics later.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(
        f"{corr_prefix} [dispatch_scans_and_processing] Starting for {scenario_id}"
    )

    scenario_repo = TrainingScenarioRepository(self.db)
    scenario = scenario_repo.find_by_id(scenario_id)

    if not scenario:
        return {"status": "error", "error": "Scenario not found"}

    # Get scan_metrics config from feature_config
    feature_config = scenario.feature_config
    if isinstance(feature_config, dict):
        scan_metrics_config = feature_config.get("scan_metrics", {})
    else:
        scan_metrics_config = getattr(feature_config, "scan_metrics", {}) or {}

    has_scans = bool(scan_metrics_config.get("sonarqube")) or bool(
        scan_metrics_config.get("trivy")
    )

    # Dispatch scans (fire-and-forget, parallel to processing)
    if has_scans:
        logger.info(f"{corr_prefix} Dispatching scans in parallel")
        dispatch_scenario_scans.delay(
            scenario_id=scenario_id,
            correlation_id=correlation_id,
        )

    # Dispatch enrichment batches for feature extraction
    dispatch_enrichment_batches.delay(
        scenario_id=scenario_id,
        correlation_id=correlation_id,
    )

    return {
        "status": "dispatched",
        "scans_dispatched": has_scans,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.dispatch_enrichment_batches",
    queue="scenario_processing",
    soft_time_limit=180,
    time_limit=240,
)
def dispatch_enrichment_batches(
    self: PipelineTask,
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Dispatch enrichment processing for INGESTED builds.

    Flow:
    1. Get INGESTED IngestionBuild records
    2. Create EnrichmentBuild for each (if not exists)
    3. Dispatch sequential chain for temporal feature support
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(
        f"{corr_prefix} [dispatch_enrichment_batches] Starting for {scenario_id}"
    )

    scenario_repo = TrainingScenarioRepository(self.db)
    ingestion_build_repo = TrainingIngestionBuildRepository(self.db)
    enrichment_build_repo = TrainingEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)

    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "error": "Scenario not found"}

    try:
        # Get INGESTED + MISSING_RESOURCE builds (both can be processed)
        ingested_builds, _ = ingestion_build_repo.find_by_scenario(
            scenario_id, status_filter=IngestionStatus.INGESTED
        )
        missing_resource_builds, _ = ingestion_build_repo.find_by_scenario(
            scenario_id, status_filter=IngestionStatus.MISSING_RESOURCE
        )

        all_builds = ingested_builds + missing_resource_builds

        if not all_builds:
            logger.warning(f"{corr_prefix} No builds to process")
            # No builds - mark as PROCESSED (user can still generate empty dataset)
            scenario_repo.update_one(
                scenario_id,
                {
                    "status": ScenarioStatus.PROCESSED.value,
                    "processing_completed_at": datetime.utcnow(),
                    "feature_extraction_completed": True,
                },
            )
            return {"status": "completed", "builds_features_extracted": 0}

        # Get raw build run data for outcome determination and temporal ordering
        raw_build_run_ids = [b.raw_build_run_id for b in all_builds]
        raw_build_runs = {
            str(r.id): r
            for r in [raw_build_run_repo.find_by_id(rid) for rid in raw_build_run_ids]
            if r is not None
        }

        # Sort by build creation time (oldest first) for temporal features
        all_builds.sort(
            key=lambda b: (
                raw_build_runs.get(str(b.raw_build_run_id)).created_at
                if raw_build_runs.get(str(b.raw_build_run_id))
                else b.created_at
            )
            or datetime.utcnow()
        )

        # Create EnrichmentBuild records
        enrichment_build_ids = []
        for build in all_builds:
            raw_run = raw_build_runs.get(str(build.raw_build_run_id))

            # Determine outcome from conclusion
            if raw_run and raw_run.conclusion:
                outcome = 1 if raw_run.conclusion.lower() == "failure" else 0
            else:
                outcome = 1 if "failure" in str(build.status).lower() else 0

            eb = enrichment_build_repo.upsert_for_ingestion_build(
                scenario_id=scenario_id,
                ingestion_build_id=str(build.id),
                raw_repo_id=str(build.raw_repo_id),
                raw_build_run_id=str(build.raw_build_run_id),
                ci_run_id=build.ci_run_id,
                commit_sha=build.commit_sha,
                repo_full_name=build.repo_full_name,
                outcome=outcome,
                build_started_at=raw_run.run_started_at if raw_run else None,
            )
            enrichment_build_ids.append(str(eb.id))

        logger.info(
            f"{corr_prefix} Created {len(enrichment_build_ids)} enrichment builds"
        )

        # Get selected features from feature_config
        feature_config = scenario.feature_config
        if isinstance(feature_config, dict):
            dag_features = feature_config.get("dag_features", [])
        else:
            dag_features = getattr(feature_config, "dag_features", []) or []

        # Expand wildcard patterns
        selected_features = _expand_feature_patterns(dag_features)

        logger.info(
            f"{corr_prefix} Feature patterns: {dag_features}, expanded to {len(selected_features)} features"
        )

        # Build sequential processing chain
        processing_tasks = [
            process_single_enrichment.si(
                scenario_id=scenario_id,
                enrichment_build_id=build_id,
                selected_features=selected_features,
                correlation_id=correlation_id,
            )
            for build_id in enrichment_build_ids
        ]

        # Chain: B1 → B2 → ... → finalize
        workflow = chain(
            *processing_tasks,
            finalize_scenario_processing.si(
                scenario_id=scenario_id,
                created_count=len(enrichment_build_ids),
                correlation_id=correlation_id,
            ),
        )

        # Error callback for chain failure
        error_callback = handle_processing_chain_error.s(
            scenario_id=scenario_id,
            correlation_id=correlation_id,
        )
        workflow.on_error(error_callback)
        workflow.apply_async()

        logger.info(
            f"{corr_prefix} Dispatched {len(processing_tasks)} builds for processing"
        )

        publish_scenario_update(
            scenario_id=scenario_id,
            status=ScenarioStatus.PROCESSING.value,
            builds_total=scenario.builds_total,
            current_phase=f"Extracting features from {len(processing_tasks)} builds",
        )

        return {
            "status": "dispatched",
            "enrichment_builds_created": len(enrichment_build_ids),
            "total_builds": len(processing_tasks),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"{corr_prefix} Error: {error_msg}")
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.FAILED.value,
                "error_message": f"Processing dispatch failed: {error_msg}",
            },
        )

        # Notify failure
        from app.services.notification_service import notify_dataset_enrichment_failed

        notify_dataset_enrichment_failed(
            db=self.db,
            scenario_id=scenario_id,
            error_message=error_msg,
            completed_count=0,
            failed_count=0,
        )
        raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.handle_processing_chain_error",
    queue="scenario_processing",
    soft_time_limit=60,
    time_limit=120,
)
def handle_processing_chain_error(
    self: PipelineTask,
    request,
    exc,
    traceback,
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Error callback for processing chain failure.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    error_msg = str(exc) if exc else "Unknown processing error"

    logger.error(
        f"{corr_prefix} Processing chain failed for {scenario_id}: {error_msg}"
    )

    enrichment_build_repo = TrainingEnrichmentBuildRepository(self.db)
    scenario_repo = TrainingScenarioRepository(self.db)

    now = datetime.utcnow()

    # Mark all IN_PROGRESS enrichment builds as FAILED
    failed_count = enrichment_build_repo.collection.update_many(
        {
            "scenario_id": ObjectId(scenario_id),
            "extraction_status": ExtractionStatus.IN_PROGRESS.value,
        },
        {
            "$set": {
                "extraction_status": ExtractionStatus.FAILED.value,
                "extraction_error": f"Chain failed: {error_msg}",
            }
        },
    ).modified_count

    # Count completed builds
    completed_count = enrichment_build_repo.collection.count_documents(
        {
            "scenario_id": ObjectId(scenario_id),
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }
    )

    if completed_count > 0:
        # Some builds completed - mark as PROCESSED (user triggers split manually)
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.PROCESSED.value,
                "builds_features_extracted": completed_count,
                "builds_failed": failed_count,
                "processing_completed_at": now,
                "feature_extraction_completed": True,
            },
        )

        # Check and notify enrichment completion (if scans also done)
        from app.services.notification_service import (
            check_and_notify_enrichment_completed,
        )

        check_and_notify_enrichment_completed(self.db, scenario_id)
    else:
        # No builds completed - mark as FAILED and notify
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.FAILED.value,
                "error_message": error_msg,
            },
        )

        # Notify failure
        from app.services.notification_service import notify_dataset_enrichment_failed

        notify_dataset_enrichment_failed(
            db=self.db,
            scenario_id=scenario_id,
            error_message=error_msg,
            completed_count=completed_count,
            failed_count=failed_count,
        )

    return {
        "status": "handled",
        "failed_builds": failed_count,
        "completed_builds": completed_count,
        "error": error_msg,
    }


@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.training_processing.process_single_enrichment",
    queue="scenario_processing",
    soft_time_limit=300,
    time_limit=600,
    max_retries=2,
)
def process_single_enrichment(
    self: SafeTask,
    scenario_id: str,
    enrichment_build_id: str,
    selected_features: List[str],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a single enrichment build for feature extraction.

    Uses extract_features_for_build helper with Hamilton DAG.
    """
    from app.entities.feature_audit_log import AuditLogCategory
    from app.tasks.shared import extract_features_for_build

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    scenario_repo = TrainingScenarioRepository(self.db)
    enrichment_build_repo = TrainingEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    # Load enrichment build
    enrichment_build = enrichment_build_repo.find_by_id(enrichment_build_id)
    if not enrichment_build:
        logger.error(f"{corr_prefix} EnrichmentBuild {enrichment_build_id} not found")
        return {"status": "error", "error": "EnrichmentBuild not found"}

    if enrichment_build.extraction_status == ExtractionStatus.COMPLETED.value:
        return {"status": "skipped", "reason": "already_processed"}

    # Load dependencies
    raw_build_run = raw_build_run_repo.find_by_id(enrichment_build.raw_build_run_id)
    if not raw_build_run:
        enrichment_build_repo.update_extraction_status(
            enrichment_build_id,
            ExtractionStatus.FAILED,
            error_message="RawBuildRun not found",
        )
        return {"status": "failed", "error": "RawBuildRun not found"}

    raw_repo = raw_repo_repo.find_by_id(raw_build_run.raw_repo_id)
    if not raw_repo:
        enrichment_build_repo.update_extraction_status(
            enrichment_build_id,
            ExtractionStatus.FAILED,
            error_message="RawRepository not found",
        )
        return {"status": "failed", "error": "RawRepository not found"}

    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "error": "Scenario not found"}

    try:
        # Mark as in progress
        enrichment_build_repo.update_extraction_status(
            enrichment_build_id,
            ExtractionStatus.IN_PROGRESS,
        )

        # Extract features using Hamilton DAG
        result = extract_features_for_build(
            db=self.db,
            raw_repo=raw_repo,
            feature_config={},
            raw_build_run=raw_build_run,
            selected_features=selected_features,
            output_build_id=enrichment_build_id,
            category=AuditLogCategory.TRAINING_SCENARIO,
            scenario_id=scenario_id,
        )

        # Update enrichment build with result
        if result["status"] == "completed":
            enrichment_build_repo.update_extraction_status(
                enrichment_build_id,
                ExtractionStatus.COMPLETED,
                feature_vector_id=result.get("feature_vector_id"),
            )
        elif result["status"] == "partial":
            enrichment_build_repo.update_extraction_status(
                enrichment_build_id,
                ExtractionStatus.PARTIAL,
                feature_vector_id=result.get("feature_vector_id"),
                error_message="; ".join(result.get("errors", [])),
            )
        else:
            enrichment_build_repo.update_extraction_status(
                enrichment_build_id,
                ExtractionStatus.FAILED,
                error_message="; ".join(result.get("errors", [])),
            )

        # Increment processed count
        scenario_repo.increment_counter(scenario_id, "builds_features_extracted")

        logger.info(
            f"{corr_prefix} [process_single] {enrichment_build_id}: "
            f"status={result['status']}, features={result.get('feature_count', 0)}"
        )

        return {
            "status": result["status"],
            "build_id": enrichment_build_id,
            "feature_count": result.get("feature_count", 0),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"{corr_prefix} Error for {enrichment_build_id}: {error_msg}")
        enrichment_build_repo.update_extraction_status(
            enrichment_build_id,
            ExtractionStatus.FAILED,
            error_message=error_msg,
        )
        scenario_repo.increment_counter(scenario_id, "builds_failed")
        raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.finalize_scenario_processing",
    queue="scenario_processing",
    soft_time_limit=60,
    time_limit=120,
)
def finalize_scenario_processing(
    self: PipelineTask,
    scenario_id: str,
    created_count: int = 0,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Finalize processing after all builds extracted.

    Marks scenario as PROCESSED. User can trigger split/download when ready.
    Does NOT auto-dispatch split - user decides when to generate dataset.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(f"{corr_prefix} [finalize_processing] Finalizing for {scenario_id}")

    scenario_repo = TrainingScenarioRepository(self.db)
    enrichment_build_repo = TrainingEnrichmentBuildRepository(self.db)

    # Get stats
    stats = enrichment_build_repo.aggregate_stats_by_scenario(scenario_id)
    completed = stats.get("completed", 0)
    partial = stats.get("partial", 0)
    failed = stats.get("failed", 0)
    total = completed + partial + failed

    # Update scenario - mark as PROCESSED (user triggers split manually)
    scenario_repo.update_one(
        scenario_id,
        {
            "status": ScenarioStatus.PROCESSED.value,
            "builds_features_extracted": completed + partial,
            "builds_failed": failed,
            "processing_completed_at": datetime.utcnow(),
            "feature_extraction_completed": True,
        },
    )

    scenario = scenario_repo.find_by_id(scenario_id)
    publish_scenario_update(
        scenario_id=scenario_id,
        status=ScenarioStatus.PROCESSED.value,
        builds_total=scenario.builds_total if scenario else total,
        builds_ingested=scenario.builds_ingested if scenario else total,
        builds_features_extracted=completed + partial,
        builds_failed=failed,
        current_phase="Feature extraction complete. Click 'Generate Dataset' when ready.",
    )

    logger.info(
        f"{corr_prefix} Completed: {completed + partial}/{total}, failed: {failed}. "
        f"Waiting for user to trigger dataset generation."
    )

    # Check if enrichment is fully complete (features + scans) and send notification
    from app.services.notification_service import check_and_notify_enrichment_completed

    check_and_notify_enrichment_completed(self.db, scenario_id)

    # NOTE: Split is NOT auto-dispatched. User triggers via generate_scenario_dataset.

    return {
        "status": "completed",
        "builds_features_extracted": completed + partial,
        "builds_failed": failed,
        "total": total,
        "next_step": "User can now generate dataset via 'Generate Dataset' button",
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.reprocess_failed_builds",
    queue="scenario_processing",
    soft_time_limit=300,
    time_limit=360,
)
def reprocess_failed_builds(
    self: PipelineTask,
    scenario_id: str,
) -> Dict[str, Any]:
    """
    Reprocess only FAILED enrichment builds for a scenario.

    Uses sequential chain to ensure temporal features work correctly.
    """
    import uuid

    correlation_id = str(uuid.uuid4())

    scenario_repo = TrainingScenarioRepository(self.db)
    enrichment_build_repo = TrainingEnrichmentBuildRepository(self.db)

    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "message": "Scenario not found"}

    # Find FAILED enrichment builds
    failed_builds, _ = enrichment_build_repo.find_by_scenario(
        scenario_id, extraction_status=ExtractionStatus.FAILED
    )

    if not failed_builds:
        return {"status": "no_failed_builds", "message": "No failed builds to retry"}

    # Reset FAILED builds to PENDING
    reset_count = 0
    for build in failed_builds:
        enrichment_build_repo.update_one(
            str(build.id),
            {
                "extraction_status": ExtractionStatus.PENDING.value,
                "extraction_error": None,
                "feature_vector_id": None,
            },
        )
        reset_count += 1

    # Get selected features from scenario
    feature_config = scenario.feature_config
    if isinstance(feature_config, dict):
        dag_features = feature_config.get("dag_features", [])
    else:
        dag_features = getattr(feature_config, "dag_features", []) or []
    selected_features = _expand_feature_patterns(dag_features)

    # Build reprocessing chain
    processing_tasks = [
        process_single_enrichment.si(
            scenario_id=scenario_id,
            enrichment_build_id=str(build.id),
            selected_features=selected_features,
            correlation_id=correlation_id,
        )
        for build in failed_builds
    ]

    workflow = chain(
        *processing_tasks,
        finalize_scenario_processing.si(
            scenario_id=scenario_id,
            created_count=0,
            correlation_id=correlation_id,
        ),
    )
    workflow.apply_async()

    logger.info(f"Dispatched reprocessing for {reset_count} failed builds")

    return {
        "status": "queued",
        "builds_reset": reset_count,
        "correlation_id": correlation_id,
    }


# ============================================================================
# SPLITTING PHASE
# ============================================================================


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.generate_scenario_dataset",
    queue="scenario_processing",
    soft_time_limit=600,
    time_limit=720,
)
def generate_scenario_dataset(
    self: PipelineTask,
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Generate dataset - User-triggered split and export.

    Validates that feature extraction is complete, then:
    - Collects features + scan_metrics from completed builds
    - Applies splitting strategy (train/val/test)
    - Exports to parquet/csv files
    """
    import uuid

    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(f"{corr_prefix} [generate_dataset] Starting for scenario {scenario_id}")

    scenario_repo = TrainingScenarioRepository(self.db)
    enrichment_build_repo = TrainingEnrichmentBuildRepository(self.db)
    split_repo = TrainingDatasetSplitRepository(self.db)

    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "error": "Scenario not found"}

    # Validate status - must be PROCESSED (feature extraction complete)
    if scenario.status not in [
        ScenarioStatus.PROCESSED.value,
        ScenarioStatus.COMPLETED.value,
    ]:
        return {
            "status": "error",
            "error": f"Cannot generate dataset: status is {scenario.status}, expected PROCESSED",
        }

    # Update status to SPLITTING
    scenario_repo.update_one(
        scenario_id,
        {
            "status": ScenarioStatus.SPLITTING.value,
            "splitting_started_at": datetime.utcnow(),
        },
    )

    publish_scenario_update(
        scenario_id=scenario_id,
        status=ScenarioStatus.SPLITTING.value,
        current_phase="Generating dataset (splitting and exporting)...",
    )

    try:
        from app.services.splitting_strategy_service import SplittingStrategyService

        # Get completed enrichment builds
        enrichment_builds = enrichment_build_repo.get_completed_with_features(
            scenario_id
        )

        if not enrichment_builds:
            logger.warning(f"{corr_prefix} No completed builds to split")
            scenario_repo.update_one(
                scenario_id,
                {
                    "status": ScenarioStatus.FAILED.value,
                    "error_message": "No completed builds to split",
                },
            )
            return {"status": "error", "error": "No completed builds"}

        # Build DataFrame from enrichment builds
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repo_ids = list({str(eb.raw_repo_id) for eb in enrichment_builds})
        raw_repos = {
            str(r.id): r
            for r in [raw_repo_repo.find_by_id(rid) for rid in raw_repo_ids]
            if r is not None
        }

        df = _build_split_dataframe(enrichment_builds, raw_repos, self.db)

        # Apply preprocessing
        preprocessing_config = getattr(scenario, "preprocessing_config", None)
        if preprocessing_config:
            from app.services.preprocessing_service import PreprocessingService

            config_dict = (
                preprocessing_config
                if isinstance(preprocessing_config, dict)
                else preprocessing_config.__dict__
            )
            preprocessing_service = PreprocessingService.from_dict(config_dict)
            df = preprocessing_service.preprocess(df)
            logger.info(f"{corr_prefix} Applied preprocessing")

        # Apply splitting strategy
        splitting_service = SplittingStrategyService()
        splitting_config = scenario.splitting_config
        if isinstance(splitting_config, dict):
            from app.entities.training_scenario import SplittingConfig

            splitting_config = SplittingConfig(**splitting_config)

        result = splitting_service.apply_split(
            df=df,
            config=splitting_config,
            label_column="outcome",
        )

        # Assign splits to enrichment builds
        id_list = df["id"].tolist()
        assignments = {
            "train": [id_list[i] for i in result.train_indices],
            "validation": [id_list[i] for i in result.val_indices],
            "test": [id_list[i] for i in result.test_indices],
        }
        enrichment_build_repo.assign_splits(scenario_id, assignments)

        # Create output directory
        output_dir = paths.get_ml_dataset_dir(scenario_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get output format
        output_config = scenario.output_config
        if isinstance(output_config, dict):
            file_format = output_config.get("format", "parquet")
        else:
            file_format = getattr(output_config, "format", "parquet") or "parquet"

        # Export split files
        split_stats = {}
        for split_type, indices in [
            ("train", result.train_indices),
            ("validation", result.val_indices),
            ("test", result.test_indices),
        ]:
            if not indices:
                continue

            split_df = df.loc[indices]
            file_path = paths.get_training_dataset_split_path(
                scenario_id, split_type, file_format
            )

            start_time = datetime.utcnow()
            if file_format == "parquet":
                split_df.to_parquet(file_path, index=False)
            elif file_format == "csv":
                split_df.to_csv(file_path, index=False)
            else:
                split_df.to_pickle(file_path)

            duration = (datetime.utcnow() - start_time).total_seconds()
            file_size = file_path.stat().st_size
            class_dist = split_df["outcome"].value_counts().to_dict()

            split_repo.create_split(
                scenario_id=scenario_id,
                split_type=split_type,
                record_count=len(split_df),
                feature_count=len(split_df.columns),
                class_distribution={str(k): v for k, v in class_dist.items()},
                group_distribution={},
                file_path=str(file_path.relative_to(paths.DATA_DIR)),
                file_size_bytes=file_size,
                file_format=file_format,
                feature_names=list(split_df.columns),
                generation_duration_seconds=duration,
            )

            split_stats[split_type] = {"count": len(split_df), "file_size": file_size}

        # Update scenario - COMPLETED
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.COMPLETED.value,
                "train_count": len(result.train_indices),
                "val_count": len(result.val_indices),
                "test_count": len(result.test_indices),
                "splitting_completed_at": datetime.utcnow(),
            },
        )

        publish_scenario_update(
            scenario_id=scenario_id,
            status=ScenarioStatus.COMPLETED.value,
            builds_total=scenario.builds_total,
            builds_ingested=scenario.builds_ingested,
            builds_features_extracted=scenario.builds_features_extracted,
            train_count=len(result.train_indices),
            val_count=len(result.val_indices),
            test_count=len(result.test_indices),
            current_phase="Dataset generation completed",
        )

        # Send completion notification
        from app.services.notification_service import (
            notify_dataset_enrichment_completed,
        )

        notify_dataset_enrichment_completed(
            db=self.db,
            user_id=scenario.created_by,
            dataset_name=scenario.name,
            scenario_id=scenario_id,
            builds_features_extracted=scenario.builds_features_extracted or 0,
            builds_total=scenario.builds_total or 0,
        )

        logger.info(
            f"{corr_prefix} Completed: train={len(result.train_indices)}, "
            f"val={len(result.val_indices)}, test={len(result.test_indices)}"
        )

        return {
            "status": "completed",
            "train_count": len(result.train_indices),
            "val_count": len(result.val_indices),
            "test_count": len(result.test_indices),
            "split_stats": split_stats,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"{corr_prefix} [split] Error: {error_msg}")
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.FAILED.value,
                "error_message": f"Splitting failed: {error_msg}",
            },
        )

        # Notify failure
        from app.services.notification_service import notify_dataset_enrichment_failed

        notify_dataset_enrichment_failed(
            db=self.db,
            scenario_id=scenario_id,
            error_message=error_msg,
            completed_count=0,
            failed_count=0,
        )
        raise


# ============================================================================
# SCAN DISPATCH TASKS
# ============================================================================


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.dispatch_scenario_scans",
    queue="scenario_scanning",
    soft_time_limit=300,
    time_limit=600,
)
def dispatch_scenario_scans(
    self: PipelineTask,
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Dispatch scans for all unique commits in scenario's ingested builds.

    Fire-and-forget: runs parallel to feature extraction.
    """
    from app.config import settings

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    scenario_repo = TrainingScenarioRepository(self.db)
    ingestion_build_repo = TrainingIngestionBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "error": "Scenario not found"}

    # Get scan_metrics config
    feature_config = scenario.feature_config
    if isinstance(feature_config, dict):
        scan_metrics_config = feature_config.get("scan_metrics", {})
    else:
        scan_metrics_config = getattr(feature_config, "scan_metrics", {}) or {}

    has_sonar = bool(scan_metrics_config.get("sonarqube"))
    has_trivy = bool(scan_metrics_config.get("trivy"))

    if not has_sonar and not has_trivy:
        logger.info(f"{corr_prefix} No scan metrics configured, skipping")
        return {"status": "skipped", "reason": "No scan metrics configured"}

    # Collect unique commits
    commits_to_scan: Dict[tuple, Dict[str, Any]] = {}
    repo_cache: Dict[str, Any] = {}

    ingested_builds, _ = ingestion_build_repo.find_by_scenario(
        scenario_id=scenario_id,
        status_filter=IngestionStatus.INGESTED,
    )

    raw_build_run_ids = [
        b.raw_build_run_id for b in ingested_builds if b.raw_build_run_id
    ]
    raw_build_runs = raw_build_run_repo.find_by_ids(raw_build_run_ids)
    build_run_map = {str(r.id): r for r in raw_build_runs}

    for build in ingested_builds:
        raw_run = build_run_map.get(str(build.raw_build_run_id))
        if not raw_run or not raw_run.commit_sha:
            continue

        commit_key = (str(build.raw_repo_id), raw_run.commit_sha)
        if commit_key in commits_to_scan:
            continue

        if str(build.raw_repo_id) not in repo_cache:
            raw_repo = raw_repo_repo.find_by_id(str(build.raw_repo_id))
            if raw_repo:
                repo_cache[str(build.raw_repo_id)] = raw_repo

        raw_repo = repo_cache.get(str(build.raw_repo_id))
        if not raw_repo:
            continue

        commits_to_scan[commit_key] = {
            "raw_repo_id": str(build.raw_repo_id),
            "github_repo_id": raw_repo.github_id,
            "commit_sha": raw_run.commit_sha,
            "repo_full_name": raw_repo.full_name,
        }

    if not commits_to_scan:
        logger.info(f"{corr_prefix} No commits to scan")
        scenario_repo.update_one(
            scenario_id, {"scans_total": 0, "scan_extraction_completed": True}
        )
        return {"status": "skipped", "reason": "No commits found"}

    # Calculate scans_total
    enabled_tools = (1 if has_sonar else 0) + (1 if has_trivy else 0)
    scans_total = len(commits_to_scan) * enabled_tools

    scenario_repo.set_scans_total(scenario_id, scans_total)

    # Split into batches
    commits_list = list(commits_to_scan.values())
    batch_size = getattr(settings, "SCAN_COMMITS_PER_BATCH", 20)
    batches = [
        commits_list[i : i + batch_size]
        for i in range(0, len(commits_list), batch_size)
    ]

    logger.info(
        f"{corr_prefix} Dispatching {len(commits_list)} commits in {len(batches)} batches"
    )

    # Chain batches
    batch_tasks = [
        process_scan_batch.s(
            scenario_id=scenario_id,
            commits_batch=batch,
            batch_index=i,
            total_batches=len(batches),
            scan_metrics_config=scan_metrics_config,
            correlation_id=correlation_id,
        )
        for i, batch in enumerate(batches)
    ]

    if batch_tasks:
        workflow = chain(
            *batch_tasks,
            finalize_scan_dispatch.si(
                scenario_id=scenario_id,
                total_commits=len(commits_list),
                total_batches=len(batches),
                has_sonar=has_sonar,
                has_trivy=has_trivy,
                correlation_id=correlation_id,
            ),
        )
        workflow.apply_async()

    publish_scenario_update(
        scenario_id=scenario_id,
        status=scenario.status if hasattr(scenario, "status") else "processing",
        scans_total=scans_total,
        scans_completed=0,
    )

    return {
        "status": "dispatched",
        "total_commits": len(commits_list),
        "scans_total": scans_total,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.process_scan_batch",
    queue="scenario_scanning",
    soft_time_limit=120,
    time_limit=180,
)
def process_scan_batch(
    self: PipelineTask,
    scenario_id: str,
    commits_batch: List[Dict[str, Any]],
    batch_index: int,
    total_batches: int,
    scan_metrics_config: Dict[str, List[str]],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a single batch of scan dispatches.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    logger.info(f"{corr_prefix} [scan_batch] Batch {batch_index + 1}/{total_batches}")

    from app.tasks.training_scan_helpers import dispatch_scan_for_scenario_commit

    dispatched = 0
    for commit_info in commits_batch:
        try:
            dispatch_scan_for_scenario_commit.delay(
                scenario_id=scenario_id,
                raw_repo_id=commit_info["raw_repo_id"],
                github_repo_id=commit_info["github_repo_id"],
                commit_sha=commit_info["commit_sha"],
                repo_full_name=commit_info["repo_full_name"],
                scan_metrics_config=scan_metrics_config,
            )
            dispatched += 1
        except Exception as e:
            logger.warning(f"{corr_prefix} Failed to dispatch: {e}")

    return {"status": "completed", "batch_index": batch_index, "dispatched": dispatched}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_processing.finalize_scan_dispatch",
    queue="scenario_scanning",
    soft_time_limit=60,
    time_limit=120,
)
def finalize_scan_dispatch(
    self: PipelineTask,
    scenario_id: str,
    total_commits: int,
    total_batches: int,
    has_sonar: bool,
    has_trivy: bool,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Finalize scan dispatch after all batches complete.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    logger.info(
        f"{corr_prefix} Scan dispatch completed: {total_commits} commits, "
        f"sonar={has_sonar}, trivy={has_trivy}"
    )

    return {
        "status": "completed",
        "total_commits": total_commits,
        "total_batches": total_batches,
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _build_split_dataframe(
    enrichment_builds: List[Any],
    raw_repos: Dict[str, Any],
    db,
) -> pd.DataFrame:
    """Build DataFrame from enrichment builds with features."""
    from app.repositories.feature_vector import FeatureVectorRepository

    fv_repo = FeatureVectorRepository(db)
    data = []

    for eb in enrichment_builds:
        raw_repo = raw_repos.get(str(eb.raw_repo_id))
        primary_language = (
            raw_repo.main_lang if raw_repo and raw_repo.main_lang else "other"
        )

        row_data = {
            "id": str(eb.id),
            "outcome": eb.outcome or 0,
            "repo_full_name": eb.repo_full_name,
            "primary_language": primary_language.lower(),
            "build_started_at": eb.build_started_at,
        }

        if eb.feature_vector_id:
            fv = fv_repo.find_by_id(str(eb.feature_vector_id))
            if fv:
                if fv.features:
                    row_data.update(fv.features)
                if fv.scan_metrics:
                    row_data.update(fv.scan_metrics)

        data.append(row_data)

    df = pd.DataFrame(data)
    df.index = range(len(df))
    return df


def _expand_feature_patterns(patterns: List[str]) -> List[str]:
    """Expand wildcard feature patterns to actual feature names."""
    from app.tasks.pipeline.feature_dag._feature_definitions import FEATURE_REGISTRY

    if not patterns:
        return list(FEATURE_REGISTRY.keys())

    expanded = set()
    for pattern in patterns:
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            for feature_name in FEATURE_REGISTRY.keys():
                if feature_name.startswith(prefix):
                    expanded.add(feature_name)
        else:
            if pattern in FEATURE_REGISTRY:
                expanded.add(pattern)

    return list(expanded) if expanded else list(FEATURE_REGISTRY.keys())
