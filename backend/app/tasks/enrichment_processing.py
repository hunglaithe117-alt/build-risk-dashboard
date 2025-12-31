"""
Version Enrichment Tasks - Chord pattern for parallel ingestion and feature extraction.

Flow (NEW - chord pattern):
1. start_enrichment - Orchestrator: Build parallel ingestion tasks
2. aggregate_ingestion_results - Chord callback: aggregate ingestion results
3. dispatch_scans_and_processing - Dispatch scans (async) + processing
4. dispatch_enrichment_batches - Dispatch batch processing
5. process_enrichment_batch - Extract features for a batch of builds
6. finalize_enrichment - Mark version as completed
7. dispatch_version_scans - Dispatch scans per unique commit (async)
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.config import settings
from app.core.tracing import TracingContext
from app.database.mongo import get_database
from app.entities.dataset_build import DatasetBuild
from app.entities.dataset_import_build import (
    DatasetImportBuild,
    DatasetImportBuildStatus,
)
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.entities.enums import ExtractionStatus
from app.entities.feature_audit_log import AuditLogCategory
from app.entities.raw_repository import RawRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_import_build import DatasetImportBuildRepository
from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.shared import extract_features_for_build
from app.tasks.shared.events import publish_enrichment_update
from app.tasks.shared.processing_tracker import ProcessingTracker

logger = logging.getLogger(__name__)


class EnrichmentTask(PipelineTask):
    """
    Custom task class for enrichment with entity failure handling.

    When a task fails (timeout, error), automatically updates
    DatasetVersion status to FAILED and publishes WebSocket event.
    """

    def get_entity_failure_handler(self, kwargs: dict) -> Optional[Callable[[str, str], None]]:
        """Update DatasetVersion status to FAILED when task fails."""
        version_id = kwargs.get("version_id")
        if not version_id:
            return None

        def update_version_failed(status: str, error_message: str) -> None:
            try:
                db = get_database()
                version_repo = DatasetVersionRepository(db)
                version_repo.mark_failed(version_id, error_message)
                # Publish WebSocket event for frontend
                publish_enrichment_update(
                    version_id=version_id,
                    status="failed",
                    error=error_message,
                )
            except Exception as e:
                logger.warning(f"Failed to update version {version_id} status: {e}")

        return update_version_failed


@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.start_enrichment",
    queue="processing",
    soft_time_limit=120,
    time_limit=180,
)
def start_enrichment(self: PipelineTask, version_id: str) -> Dict[str, Any]:
    """
    Orchestrator: Build ingestion chains and dispatch as chord.

    Flow (pure Celery chord pattern):
        start_enrichment
            └── chord(
                    group(
                        chain(clone_1 → worktrees_1 → logs_1),
                        chain(clone_2 → worktrees_2 → logs_2),
                        ...
                    ),
                    chain(aggregate_ingestion_results, dispatch_scans_and_processing)
                )

    Chains are built directly here (not wrapped in tasks) so chord properly
    waits for ALL chain tasks to complete before calling the callback.
    """
    from app.tasks.pipeline.feature_dag._metadata import get_required_resources_for_features
    from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
    from app.tasks.shared import build_ingestion_workflow

    # Generate correlation_id for entire enrichment run
    correlation_id = str(uuid.uuid4())

    # Set tracing context for structured logging
    TracingContext.set(
        correlation_id=correlation_id,
        version_id=version_id,
        pipeline_type="dataset_enrichment",
    )

    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    dataset_repo = DatasetRepository(self.db)
    dataset_repo_stats_repo = DatasetRepoStatsRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)

    # Load version
    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        logger.error(f"Version {version_id} not found")
        return {"status": "error", "error": "Version not found"}

    # Mark as started
    version_repo.mark_started(version_id, task_id=self.request.id)

    try:
        # Load dataset
        dataset = dataset_repo.find_by_id(dataset_version.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_version.dataset_id} not found")

        # Get validated builds
        validated_builds = dataset_build_repo.find_validated_builds(dataset_version.dataset_id)

        total_rows = len(validated_builds)
        if total_rows == 0:
            raise ValueError("No validated builds found. Please run validation first.")

        # Get validated repos from dataset stats
        repo_stats_list = dataset_repo_stats_repo.find_by_dataset(dataset_version.dataset_id)
        validated_raw_repo_ids = [str(stat.raw_repo_id) for stat in repo_stats_list]

        version_repo.update_one(
            version_id,
            {
                "total_rows": total_rows,
                "repos_total": len(validated_raw_repo_ids),
                "status": VersionStatus.INGESTING.value,
            },
        )
        # Publish initial progress via WebSocket
        publish_enrichment_update(
            version_id=version_id,
            status="ingesting",
            processed_rows=0,
            total_rows=total_rows,
        )
        logger.info(
            f"[start_enrichment] {total_rows} builds, "
            f"{len(validated_raw_repo_ids)} repos to ingest"
        )

        if not validated_raw_repo_ids:
            # No repos to process
            version_repo.mark_completed(version_id)
            return {"status": "completed", "message": "No repos to ingest"}

        # Calculate required resources from features
        feature_set = (
            set(dataset_version.selected_features) if dataset_version.selected_features else set()
        )
        required_resources = get_required_resources_for_features(feature_set)

        # FORCE worktree if scans are enabled
        has_scans = bool(dataset_version.scan_metrics.get("sonarqube")) or bool(
            dataset_version.scan_metrics.get("trivy")
        )
        if has_scans and "git_worktree" not in required_resources:
            required_resources.add("git_worktree")

        # Get tasks grouped by level from resource_dag
        tasks_by_level = get_ingestion_tasks_by_level(list(required_resources))

        logger.info(
            f"[start_enrichment] Resources={required_resources}, "
            f"tasks_by_level={tasks_by_level}, scans={has_scans}"
        )

        # Create DatasetImportBuild records for tracking ingestion per-build
        import_builds_created = _create_import_builds_for_version(
            db=self.db,
            version_id=version_id,
            validated_builds=validated_builds,
            required_resources=list(required_resources),
        )
        logger.info(f"[start_enrichment] Created {import_builds_created} import build records")

        # Build INGESTION CHAINS directly (not wrapped in tasks)
        # This ensures chord properly waits for all chain tasks
        ingestion_chains = []
        repo_metadata = []  # Track metadata for aggregation

        for raw_repo_id in validated_raw_repo_ids:
            # Get repo info
            raw_repo = raw_repo_repo.find_by_id(raw_repo_id)
            if not raw_repo:
                logger.warning(f"RawRepository {raw_repo_id} not found, skipping")
                continue

            # Get CI provider from repo stats
            repo_stats = dataset_repo_stats_repo.find_by_dataset_and_repo(
                str(dataset.id), raw_repo_id
            )
            ci_provider = "github_actions"
            if repo_stats and repo_stats.ci_provider:
                ci_provider = (
                    repo_stats.ci_provider.value
                    if hasattr(repo_stats.ci_provider, "value")
                    else repo_stats.ci_provider
                )

            # Get build IDs and commit SHAs for this repo
            repo_builds = dataset_build_repo.find_found_builds_by_repo(
                dataset_version.dataset_id, raw_repo_id
            )
            build_csv_ids = list({str(build.build_id_from_csv) for build in repo_builds})

            if not build_csv_ids:
                continue

            # Get commit SHAs
            commit_shas = []
            for build_csv_id in build_csv_ids:
                raw_build_run = raw_build_run_repo.find_by_business_key(
                    raw_repo_id, build_csv_id, ci_provider
                )
                if raw_build_run and raw_build_run.commit_sha:
                    commit_shas.append(raw_build_run.effective_sha or raw_build_run.commit_sha)
            commit_shas = list(set(commit_shas))

            # Build ingestion chain for this repo
            repo_chain = build_ingestion_workflow(
                tasks_by_level=tasks_by_level,
                raw_repo_id=raw_repo_id,
                github_repo_id=raw_repo.github_repo_id,
                full_name=raw_repo.full_name,
                build_ids=build_csv_ids,
                commit_shas=commit_shas,
                ci_provider=ci_provider,
            )

            if repo_chain:
                ingestion_chains.append(repo_chain)
                repo_metadata.append(
                    {
                        "raw_repo_id": raw_repo_id,
                        "full_name": raw_repo.full_name,
                        "builds": len(build_csv_ids),
                        "commits": len(commit_shas),
                    }
                )
                logger.info(
                    f"[start_enrichment] Built chain for {raw_repo.full_name}: "
                    f"{len(build_csv_ids)} builds, {len(commit_shas)} commits"
                )

        if not ingestion_chains:
            # No ingestion needed (no tasks required for features)
            logger.info("[start_enrichment] No ingestion chains needed, proceeding to processing")
            # Mark import builds as INGESTED since no ingestion is needed
            import_build_repo = DatasetImportBuildRepository(self.db)
            import_build_repo.mark_ingested_batch(version_id)
            dispatch_scans_and_processing.delay(version_id, correlation_id=correlation_id)
            return {"status": "dispatched", "message": "No ingestion needed, dispatched processing"}

        # Initialize resource status for all import builds before ingestion
        import_build_repo = DatasetImportBuildRepository(self.db)
        init_count = import_build_repo.init_resource_status(version_id, list(required_resources))
        logger.info(f"[start_enrichment] Initialized resource status for {init_count} builds")

        # Use chord: run all repo ingestion chains in parallel → aggregate results
        # Note: chord waits for ALL chains to complete (including retries/failures)
        # Processing is NOT auto-dispatched - user triggers Phase 2 manually
        callback = aggregate_ingestion_results.s(
            version_id=version_id,
            correlation_id=correlation_id,
        )

        # Error callback for chord failures
        error_callback = handle_enrichment_chord_error.s(
            version_id=version_id,
            correlation_id=correlation_id,
        )

        chord(group(ingestion_chains), callback).apply_async(link_error=error_callback)

        logger.info(
            f"[start_enrichment] Dispatched {len(ingestion_chains)} ingestion chains "
            f"for version {version_id}"
        )

        return {
            "status": "dispatched",
            "total_builds": total_rows,
            "repos": len(validated_raw_repo_ids),
            "ingestion_chains": len(ingestion_chains),
            "repo_metadata": repo_metadata,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Version enrichment start failed: {error_msg}")
        version_repo.mark_failed(version_id, error_msg)
        raise


# Task 1b: Aggregate ingestion results (chord callback)
@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.aggregate_ingestion_results",
    queue="processing",
    soft_time_limit=30,
    time_limit=60,
)
def aggregate_ingestion_results(
    self: PipelineTask,
    results: List[Dict[str, Any]],
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Aggregate results from parallel repo ingestion chains.

    This is the chord callback that runs after ALL ingestion chains complete.
    Parses results to update per-resource status, then marks builds as INGESTED/FAILED.
    Does NOT auto-dispatch processing - user triggers Phase 2 manually.
    """
    from bson import ObjectId

    from app.entities.dataset_import_build import ResourceStatus
    from app.tasks.pipeline.shared.resources import FeatureResource

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    import_build_repo = DatasetImportBuildRepository(self.db)

    # Collect failed items from task results (same as model pipeline)
    clone_failed = False
    clone_error = None
    failed_commits: list[str] = []
    failed_log_ids: list[str] = []
    expired_log_ids: list[str] = []

    if isinstance(results, list):
        for r in results:
            if not isinstance(r, dict):
                continue
            # Check clone result (git_history) - affects ALL builds
            if r.get("status") == "failed" and "Clone" in r.get("error", ""):
                clone_failed = True
                clone_error = r.get("error")
            if r.get("status") in ("timeout", "failed") and r.get("path") is None:
                clone_failed = True
                clone_error = r.get("error")

            # Collect failed commits from worktree chunks
            if "failed_commits" in r:
                failed_commits.extend(r["failed_commits"])

            # Collect failed log IDs from log chunks
            if "failed_log_ids" in r:
                failed_log_ids.extend(r["failed_log_ids"])
            if "expired_log_ids" in r:
                expired_log_ids.extend(r["expired_log_ids"])

    elif isinstance(results, dict):
        if results.get("status") == "failed":
            clone_failed = True
            clone_error = results.get("error")

    # === Update resource status per-build ===

    # 1. git_history: ALL builds get same status (clone is repo-level)
    if clone_failed:
        import_build_repo.update_resource_status_batch(
            version_id,
            FeatureResource.GIT_HISTORY.value,
            ResourceStatus.FAILED,
            clone_error,
        )
    else:
        import_build_repo.update_resource_status_batch(
            version_id, FeatureResource.GIT_HISTORY.value, ResourceStatus.COMPLETED
        )

    # 2. git_worktree: Mark failed commits, then mark rest as completed
    if failed_commits:
        # Note: update_resource_by_commits needs raw_repo_id; for dataset we update all
        # builds with matching commit_sha
        import_build_repo.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "commit_sha": {"$in": failed_commits},
            },
            {
                "$set": {
                    f"resource_status.{FeatureResource.GIT_WORKTREE.value}.status": ResourceStatus.FAILED.value,
                    f"resource_status.{FeatureResource.GIT_WORKTREE.value}.error": "Worktree creation failed",
                }
            },
        )
    # Mark remaining as completed
    import_build_repo.update_resource_status_batch(
        version_id, FeatureResource.GIT_WORKTREE.value, ResourceStatus.COMPLETED
    )

    # 3. build_logs: Mark failed/expired logs, then mark rest as completed
    all_failed_logs = failed_log_ids + expired_log_ids
    if all_failed_logs:
        import_build_repo.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "ci_run_id": {"$in": all_failed_logs},
            },
            {
                "$set": {
                    f"resource_status.{FeatureResource.BUILD_LOGS.value}.status": ResourceStatus.FAILED.value,
                    f"resource_status.{FeatureResource.BUILD_LOGS.value}.error": "Log download failed or expired",
                }
            },
        )
    # Mark remaining as completed
    import_build_repo.update_resource_status_batch(
        version_id, FeatureResource.BUILD_LOGS.value, ResourceStatus.COMPLETED
    )

    # === Determine per-build final status ===
    # A build is INGESTED if all required resources are COMPLETED
    # A build is FAILED if any required resource is FAILED

    # Mark builds as MISSING_RESOURCE if clone failed (all builds)
    if clone_failed:
        import_build_repo.update_many_by_status(
            version_id,
            from_status=DatasetImportBuildStatus.INGESTING.value,
            updates={"status": DatasetImportBuildStatus.MISSING_RESOURCE.value},
        )
    else:
        # Mark builds with failed worktrees as MISSING_RESOURCE
        if failed_commits:
            import_build_repo.collection.update_many(
                {
                    "dataset_version_id": ObjectId(version_id),
                    "status": DatasetImportBuildStatus.INGESTING.value,
                    "commit_sha": {"$in": failed_commits},
                },
                {"$set": {"status": DatasetImportBuildStatus.MISSING_RESOURCE.value}},
            )
        # Mark remaining INGESTING builds as INGESTED
        import_build_repo.mark_ingested_batch(version_id)

    # Count by status to determine final state
    status_counts = import_build_repo.count_by_status(version_id)
    ingested = status_counts.get(DatasetImportBuildStatus.INGESTED.value, 0)
    missing_resource = status_counts.get(DatasetImportBuildStatus.MISSING_RESOURCE.value, 0)

    # Determine final ingestion status
    # Note: MISSING_RESOURCE builds can still be processed (graceful degradation)
    # Always set to INGESTED - missing_resource count is tracked in repos_failed
    final_status = VersionStatus.INGESTED
    if missing_resource > 0:
        msg = f"Ingestion complete with warnings: {ingested} ok, {missing_resource} missing resources. Start processing when ready."
    else:
        msg = f"Ingestion complete: {ingested} builds ready. Start processing when ready."

    version_repo.update_one(
        version_id,
        {
            "status": final_status.value,
            "ingestion_progress": 100,
            "repos_ingested": ingested,
            "repos_failed": missing_resource,
        },
    )

    logger.info(f"{corr_prefix}[aggregate_ingestion_results] {msg}")

    # Get resource status summary for stats
    resource_summary = import_build_repo.get_resource_status_summary(version_id)

    # Publish event for frontend
    publish_enrichment_update(
        version_id=version_id,
        status=final_status.value,
        processed_rows=0,
        total_rows=ingested + missing_resource,
    )

    return {
        "status": "completed",
        "final_status": final_status.value,
        "builds_ingested": ingested,
        "builds_missing_resource": missing_resource,
        "resource_status": resource_summary,
    }


# Task 1c: Error callback for ingestion chord failure
@celery_app.task(
    bind=True,
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.handle_enrichment_chord_error",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def handle_enrichment_chord_error(
    self: PipelineTask,
    request,
    exc,
    traceback,
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Error callback for ingestion chord failure.

    When ingestion chord fails (clone_repo, create_worktrees, etc.):
    1. Mark all INGESTING builds as MISSING_RESOURCE with error
    2. Update version status to INGESTED or FAILED
    3. User can review and retry
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    error_msg = str(exc) if exc else "Unknown ingestion error"

    logger.error(f"{corr_prefix} Ingestion chord failed for version {version_id}: {error_msg}")

    import_build_repo = DatasetImportBuildRepository(self.db)
    version_repo = DatasetVersionRepository(self.db)

    # Mark all INGESTING builds as MISSING_RESOURCE
    missing_resource_count = import_build_repo.update_many_by_status(
        version_id,
        from_status=DatasetImportBuildStatus.INGESTING.value,
        updates={
            "status": DatasetImportBuildStatus.MISSING_RESOURCE.value,
        },
    )

    logger.warning(f"{corr_prefix} Marked {missing_resource_count} builds as MISSING_RESOURCE")

    # Check if any builds made it to INGESTED before failure
    ingested_builds = import_build_repo.find_ingested_builds(version_id)

    if ingested_builds:
        # Some builds made it through - still mark as INGESTED
        logger.info(
            f"{corr_prefix} {len(ingested_builds)} builds were INGESTED before failure. "
            f"Processing can still proceed."
        )
        version_repo.update_one(
            version_id,
            {
                "status": VersionStatus.INGESTED.value,
                "repos_ingested": len(ingested_builds),
                "repos_failed": missing_resource_count,
            },
        )
        publish_enrichment_update(
            version_id=version_id,
            status=VersionStatus.INGESTED.value,
        )
    else:
        # No builds made it - mark as failed
        version_repo.mark_failed(version_id, error_msg)
        publish_enrichment_update(
            version_id=version_id,
            status="failed",
            error=error_msg,
        )

    return {
        "status": "handled",
        "missing_resource_builds": missing_resource_count,
        "ingested_builds": len(ingested_builds) if ingested_builds else 0,
        "error": error_msg,
    }


# Task 1d: Start processing phase (manually triggered by user)
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
    import uuid

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
def dispatch_scans_and_processing(self: PipelineTask, version_id: str) -> Dict[str, Any]:
    """
    Dispatch scans (async, fire & forget) and processing after ingestion completes.

    Scans run independently without blocking feature extraction.
    Scan results are backfilled to DatasetEnrichmentBuild.features later.
    """
    # Get correlation_id for propagation to child tasks
    correlation_id = TracingContext.get_correlation_id()
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


# Task 1e: Error callback for processing chain failure
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
    from bson import ObjectId

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


# Task 2: Dispatch enrichment batches after ingestion
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
    from celery import chain

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
    raw_build_run_ids = [str(ib.raw_build_run_id) for ib in ingested_imports]
    raw_build_runs = raw_build_run_repo.find_by_ids(raw_build_run_ids)
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
            dataset_build_id=str(import_build.dataset_build_id),
            dataset_import_build_id=str(import_build.id),
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
        total_rows=total_builds,
    )

    return {
        "status": "dispatched",
        "total_builds": total_builds,
        "created": created_count,
        "skipped": skipped_existing,
    }


# Task 2a: Process single enrichment build (for sequential chain)
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
    from app.entities.feature_audit_log import AuditLogCategory

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
    version_repo.increment_processed_rows(version_id)

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


# =============================================================================
# FAILED BUILD HANDLING (matching model pipeline)
# =============================================================================


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
    import uuid

    from celery import chain

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
    name="app.tasks.version_enrichment.reingest_missing_resource_builds",
    queue="processing",
    soft_time_limit=300,
    time_limit=360,
)
def reingest_missing_resource_builds(
    self: PipelineTask,
    version_id: str,
) -> Dict[str, Any]:
    """
    Re-ingest only MISSING_RESOURCE import builds for a version.

    This is useful when:
    - Some builds have missing resources due to transient errors
    - Clone/worktree/log download failures that may be recoverable
    """
    import uuid

    from app.entities.dataset_import_build import DatasetImportBuildStatus

    correlation_id = str(uuid.uuid4())

    version_repo = DatasetVersionRepository(self.db)
    import_build_repo = DatasetImportBuildRepository(self.db)

    # Validate version exists
    version = version_repo.find_by_id(version_id)
    if not version:
        return {"status": "error", "message": "Version not found"}

    # Find MISSING_RESOURCE import builds
    missing_resource_imports = import_build_repo.find_many(
        {
            "dataset_version_id": ObjectId(version_id),
            "status": DatasetImportBuildStatus.MISSING_RESOURCE.value,
        }
    )

    if not missing_resource_imports:
        return {
            "status": "completed",
            "builds_queued": 0,
            "message": "No missing resource builds to retry",
        }

    # Reset to PENDING
    reset_count = 0
    for build in missing_resource_imports:
        try:
            import_build_repo.update_one(
                str(build.id),
                {"status": DatasetImportBuildStatus.PENDING.value},
            )
            reset_count += 1
        except Exception as e:
            logger.warning(f"Failed to reset import build {build.id}: {e}")

    if reset_count == 0:
        return {"status": "error", "message": "Failed to reset any builds"}

    # Update version status
    version_repo.update_one(version_id, {"status": VersionStatus.INGESTING.value})

    # Re-trigger ingestion for this version
    start_enrichment.delay(version_id)

    logger.info(f"Re-triggered ingestion for {reset_count} missing resource imports")

    return {
        "status": "queued",
        "builds_reset": reset_count,
        "total_missing_resource": len(missing_resource_imports),
        "correlation_id": correlation_id,
    }


# Task 3: Finalize
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
            "processed_rows": total,
            "enriched_rows": completed + partial,
            "failed_rows": failed,
        },
    )

    # Publish completion via WebSocket
    publish_enrichment_update(
        version_id=version_id,
        status=final_status.value,
        processed_rows=total,
        enriched_rows=completed + partial,
        failed_rows=failed,
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
        "enriched_rows": completed + partial,
        "failed_rows": failed,
        "total_rows": total,
        "tracker_stats": {
            "success": tracker_success,
            "failed": tracker_failed,
            "skipped": tracker_skipped,
        },
    }


def _extract_features_for_enrichment(
    db,
    dataset_build: DatasetBuild,
    selected_features: List[str],
    raw_build_run_repo: RawBuildRunRepository,
    dataset_version: DatasetVersion,
    raw_repo: RawRepository,
    enrichment_build_id: str = None,
) -> Dict[str, Any]:
    """
    Extract features for a single build using shared helper.

    Args:
        db: Database connection
        dataset_build: DatasetBuild entity
        selected_features: Features to extract
        raw_build_run_repo: Repository for RawBuildRun lookup
        dataset_version: DatasetVersion entity (used for config via feature_configs)
        raw_repo: RawRepository (passed from caller, no lookup needed)
        enrichment_build_id: ID of the enrichment build for audit log linking

    Returns result dict with status, features, errors, warnings.
    """
    if not dataset_build.raw_run_id:
        logger.warning(f"Build {dataset_build.build_id_from_csv} has no raw_run_id")
        return {
            "status": "failed",
            "features": {},
            "errors": ["No raw_run_id"],
            "warnings": [],
        }

    raw_build_run = raw_build_run_repo.find_by_id(dataset_build.raw_run_id)
    if not raw_build_run:
        logger.warning(f"RawBuildRun with id={dataset_build.raw_run_id} not found")
        return {
            "status": "failed",
            "features": {},
            "errors": ["RawBuildRun not found"],
            "warnings": [],
        }

    # Create GitHub client for GITHUB_API features (required)
    from app.services.github.github_client import get_public_github_client
    from app.tasks.pipeline.feature_dag._inputs import GitHubClientInput

    github_client = get_public_github_client()
    github_client_input = GitHubClientInput(client=github_client, full_name=raw_repo.full_name)

    return extract_features_for_build(
        db=db,
        raw_repo=raw_repo,
        feature_config=dataset_version.feature_configs,
        raw_build_run=raw_build_run,
        selected_features=selected_features,
        github_client=github_client_input,
        category=AuditLogCategory.DATASET_ENRICHMENT,
        version_id=str(dataset_version.id),
        dataset_id=str(dataset_version.dataset_id),
        output_build_id=enrichment_build_id,
    )


def _create_import_builds_for_version(
    db,
    version_id: str,
    validated_builds: List[DatasetBuild],
    required_resources: List[str],
) -> int:
    """
    Create DatasetImportBuild records for all validated builds in a version.

    Args:
        db: Database connection
        version_id: DatasetVersion ID
        validated_builds: List of validated DatasetBuild entities
        required_resources: List of required resource names for ingestion

    Returns:
        Number of import build records created
    """
    import_build_repo = DatasetImportBuildRepository(db)
    raw_build_run_repo = RawBuildRunRepository(db)
    raw_repo_repo = RawRepositoryRepository(db)

    import_builds = []

    for dataset_build in validated_builds:
        # Skip builds without raw references
        if not dataset_build.raw_run_id or not dataset_build.raw_repo_id:
            continue

        # Get raw build run for denormalized fields
        raw_build_run = raw_build_run_repo.find_by_id(dataset_build.raw_run_id)
        if not raw_build_run:
            continue

        # Get raw repo for full_name
        raw_repo = raw_repo_repo.find_by_id(dataset_build.raw_repo_id)
        repo_full_name = raw_repo.full_name if raw_repo else ""

        import_build = DatasetImportBuild(
            _id=None,
            dataset_version_id=ObjectId(version_id),
            dataset_build_id=dataset_build.id,
            raw_repo_id=dataset_build.raw_repo_id,
            raw_build_run_id=dataset_build.raw_run_id,
            status=DatasetImportBuildStatus.PENDING,
            resource_status={},
            required_resources=required_resources,
            ci_run_id=raw_build_run.ci_run_id or "",
            commit_sha=raw_build_run.effective_sha or raw_build_run.commit_sha or "",
            repo_full_name=repo_full_name,
        )
        import_builds.append(import_build)

    if import_builds:
        import_build_repo.bulk_insert(import_builds)
        logger.info(
            f"[_create_import_builds] Created {len(import_builds)} import builds "
            f"for version {version_id}"
        )

    return len(import_builds)


# Task 4: Dispatch version scans (runs in parallel with ingestion)
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
    import time

    from app.repositories.dataset_build_repository import DatasetBuildRepository

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
    commits_to_scan = {}  # {(repo_id, commit_sha): commit_info}
    repo_cache = {}  # Cache RawRepository lookups

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


# Task 5: Process version export job (for large dataset version exports)
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
    import os
    from datetime import timezone

    from app.repositories.export_job import ExportJobRepository
    from app.utils.export_utils import write_csv_file, write_json_file

    job_repo = ExportJobRepository(self.db)
    enrichment_repo = DatasetEnrichmentBuildRepository(self.db)

    job = job_repo.find_by_id(job_id)
    if not job:
        logger.error(f"Export job {job_id} not found")
        return {"status": "error", "message": "Job not found"}

    # Mark as processing
    job_repo.update_status(job_id, "processing")

    try:
        # Get data cursor
        cursor = enrichment_repo.get_enriched_for_export(
            dataset_id=job.dataset_id,
            version_id=job.version_id,
        )

        # Get all feature keys for CSV headers
        all_feature_keys = enrichment_repo.get_all_feature_keys(
            dataset_id=job.dataset_id,
            version_id=job.version_id,
        )

        # Prepare output path
        from app.utils.export_utils import format_feature_row

        export_dir = os.path.join(settings.REPO_DATA_DIR, "exports")
        os.makedirs(export_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"version_{job.version_id}_{timestamp}.{job.format}"
        file_path = os.path.join(export_dir, filename)

        # Progress callback
        def update_progress(processed: int) -> None:
            if processed % 500 == 0:  # Update every 500 rows
                job_repo.update_progress(job_id, processed)

        # Write file
        if job.format == "csv":
            write_csv_file(
                cursor=cursor,
                format_row=format_feature_row,
                output_path=file_path,
                selected_features=job.features,
                all_feature_keys=all_feature_keys,
                progress_callback=update_progress,
            )
        else:
            write_json_file(
                cursor=cursor,
                format_row=format_feature_row,
                output_path=file_path,
                selected_features=job.features,
                progress_callback=update_progress,
            )

        # Get file size
        file_size = os.path.getsize(file_path)

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
