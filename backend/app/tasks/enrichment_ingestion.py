"""
Version Enrichment Ingestion Tasks - Phase 1: Clone, Worktree, Logs.

This module handles the ingestion phase of dataset version enrichment:
1. start_enrichment - Orchestrator: Build parallel ingestion tasks
2. aggregate_ingestion_results - Chord callback: aggregate ingestion results
3. handle_enrichment_chord_error - Error handler for ingestion failures
4. dispatch_version_scans - Dispatch scans per unique commit (async)
5. reingest_failed_builds - Retry FAILED builds

After ingestion completes, user triggers Phase 2 (processing) via
start_enrichment_processing in enrichment_processing.py.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.core.tracing import TracingContext
from app.entities.dataset_import_build import (
    DatasetImportBuild,
    DatasetImportBuildStatus,
)
from app.entities.dataset_version import VersionStatus
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_import_build import DatasetImportBuildRepository
from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.shared.events import publish_enrichment_update

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.start_enrichment",
    queue="dataset_ingestion",
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
                    aggregate_ingestion_results
                )

    After ingestion completes, version is marked as INGESTED.
    User triggers processing (Phase 2) manually via start_enrichment_processing.

    Chains are built directly here (not wrapped in tasks) so chord properly
    waits for ALL chain tasks to complete before calling the callback.
    """
    from app.tasks.pipeline.feature_dag._metadata import (
        get_required_resources_for_features,
    )
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

    try:
        # Load dataset
        dataset = dataset_repo.find_by_id(dataset_version.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_version.dataset_id} not found")

        # builds_total is already set during version creation from validation_stats
        builds_total = dataset_version.builds_total
        if builds_total == 0:
            raise ValueError("No validated builds found. Please run validation first.")

        # Get validated repos from dataset stats
        repo_stats_list = dataset_repo_stats_repo.find_by_dataset(
            str(dataset_version.dataset_id)
        )
        validated_raw_repo_ids = [str(stat.raw_repo_id) for stat in repo_stats_list]

        # Mark as started ingestion
        version_repo.update_one(
            version_id,
            {
                "status": VersionStatus.INGESTING.value,
                "started_at": datetime.utcnow(),
                "task_id": self.request.id,
            },
        )
        # Publish initial progress via WebSocket
        publish_enrichment_update(
            version_id=version_id,
            status="ingesting",
            builds_features_extracted=0,
            builds_total=builds_total,
        )
        logger.info(
            f"[start_enrichment] {builds_total} builds, "
            f"{len(validated_raw_repo_ids)} repos to ingest"
        )

        if not validated_raw_repo_ids:
            # No repos to process
            version_repo.mark_completed(version_id)
            return {"status": "completed", "message": "No repos to ingest"}

        # Calculate required resources from features
        feature_set = (
            set(dataset_version.selected_features)
            if dataset_version.selected_features
            else set()
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
            dataset_id=str(dataset_version.dataset_id),
            required_resources=list(required_resources),
        )
        logger.info(
            f"[start_enrichment] Created {import_builds_created} import build records"
        )

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
                str(dataset_version.dataset_id), raw_repo_id
            )
            build_csv_ids = list(
                {str(build.build_id_from_csv) for build in repo_builds}
            )

            if not build_csv_ids:
                continue

            # Get commit SHAs
            commit_shas = []
            for build_csv_id in build_csv_ids:
                raw_build_run = raw_build_run_repo.find_by_business_key(
                    raw_repo_id, build_csv_id, ci_provider
                )
                if raw_build_run and raw_build_run.commit_sha:
                    commit_shas.append(raw_build_run.commit_sha)
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
                pipeline_id=version_id,
                pipeline_type="dataset",
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
            logger.info(
                "[start_enrichment] No ingestion chains needed, marking as ingested"
            )
            # Mark import builds as INGESTED since no ingestion is needed
            import_build_repo = DatasetImportBuildRepository(self.db)
            import_build_repo.mark_ingested_batch(version_id)

            # Mark version as INGESTED - user triggers processing manually
            version_repo.update_one(
                version_id,
                {
                    "status": VersionStatus.INGESTED.value,
                },
            )
            publish_enrichment_update(
                version_id=version_id,
                status=VersionStatus.INGESTED.value,
                builds_features_extracted=0,
                builds_total=builds_total,
            )
            return {
                "status": "completed",
                "message": "Ingestion complete. Start processing when ready.",
            }

        # Initialize resource status for all import builds before ingestion
        import_build_repo = DatasetImportBuildRepository(self.db)
        init_count = import_build_repo.init_resource_status(
            version_id, list(required_resources)
        )
        logger.info(
            f"[start_enrichment] Initialized resource status for {init_count} builds"
        )

        # Use chord: run all repo ingestion chains in parallel → aggregate results
        # Note: chord waits for ALL chains to complete (including retries/failures)
        # Processing is NOT auto-dispatched - user triggers Phase 2 manually
        callback = aggregate_ingestion_results.s(
            version_id=version_id,
            correlation_id=correlation_id,
        )

        # Error callback for chord failures - attach to callback, not group
        error_callback = handle_enrichment_chord_error.s(
            version_id=version_id,
            correlation_id=correlation_id,
        )

        # Use on_error on the callback task, then apply chord
        callback_with_error = callback.on_error(error_callback)
        chord(group(ingestion_chains), callback_with_error).apply_async()

        logger.info(
            f"[start_enrichment] Dispatched {len(ingestion_chains)} ingestion chains "
            f"for version {version_id}"
        )

        return {
            "status": "dispatched",
            "total_builds": builds_total,
            "repos": len(validated_raw_repo_ids),
            "ingestion_chains": len(ingestion_chains),
            "repo_metadata": repo_metadata,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Version enrichment start failed: {error_msg}")
        version_repo.mark_failed(version_id, error_msg)
        raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.aggregate_ingestion_results",
    queue="dataset_ingestion",
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
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    import_build_repo = DatasetImportBuildRepository(self.db)

    from datetime import datetime

    now = datetime.utcnow()

    # === Determine per-build final status from resource_status in DB ===
    # FAILED: Any required resource has status = "failed" (actual error - RETRYABLE)
    # MISSING_RESOURCE: Logs expired (expected - NOT RETRYABLE)
    # INGESTED: All required resources completed

    # 1. Check if git_history failed (affects ALL builds)
    git_history_failed = import_build_repo.collection.count_documents(
        {
            "dataset_version_id": ObjectId(version_id),
            "status": DatasetImportBuildStatus.INGESTING.value,
            "resource_status.git_history.status": "failed",
        }
    )

    if git_history_failed > 0:
        # Clone failed - mark all as FAILED
        import_build_repo.update_many_by_status(
            version_id,
            from_status=DatasetImportBuildStatus.INGESTING.value,
            updates={
                "status": DatasetImportBuildStatus.FAILED.value,
                "ingestion_error": "Clone failed",
                "ingested_at": now,
            },
        )
    else:
        # 2. Mark builds with failed git_worktree as FAILED
        import_build_repo.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "resource_status.git_worktree.status": "failed",
            },
            {
                "$set": {
                    "status": DatasetImportBuildStatus.FAILED.value,
                    "ingestion_error": "Worktree creation failed",
                    "ingested_at": now,
                }
            },
        )

        # 3. Mark builds with failed build_logs as MISSING_RESOURCE (not retryable)
        # Set both ingested_at (ingestion completed with partial resources) and ingested_at
        # (when the resource failure occurred) so UI can display both timestamps
        import_build_repo.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "resource_status.build_logs.status": "failed",
            },
            {
                "$set": {
                    "status": DatasetImportBuildStatus.MISSING_RESOURCE.value,
                    "ingestion_error": "Log download failed or expired",
                    "ingested_at": now,  # Ingestion completed (with partial resources)
                }
            },
        )

        # 4. Mark remaining INGESTING builds as INGESTED
        import_build_repo.mark_ingested_batch(version_id)

    # Count by status to determine final state
    status_counts = import_build_repo.count_by_status(version_id)
    ingested = status_counts.get(DatasetImportBuildStatus.INGESTED.value, 0)
    missing_resource = status_counts.get(
        DatasetImportBuildStatus.MISSING_RESOURCE.value, 0
    )
    failed = status_counts.get(DatasetImportBuildStatus.FAILED.value, 0)

    # Determine final ingestion status
    # Note: MISSING_RESOURCE and FAILED builds can still be processed (graceful degradation)
    final_status = VersionStatus.INGESTED
    if failed > 0 or missing_resource > 0:
        parts = [f"{ingested} ready"]
        if failed > 0:
            parts.append(f"{failed} failed (retryable)")
        if missing_resource > 0:
            parts.append(f"{missing_resource} missing resources")
        msg = f"Ingestion done: {', '.join(parts)}. Start processing when ready."
    else:
        msg = (
            f"Ingestion complete: {ingested} builds ready. Start processing when ready."
        )

    total_builds = ingested + missing_resource + failed
    version_repo.update_one(
        version_id,
        {
            "status": final_status.value,
            "builds_ingested": ingested,
            "builds_missing_resource": missing_resource,
            "builds_ingestion_failed": failed,
        },
    )

    logger.info(f"{corr_prefix}[aggregate_ingestion_results] {msg}")

    # Get resource status summary for stats
    resource_summary = import_build_repo.get_resource_status_summary(version_id)

    # Publish event for frontend
    publish_enrichment_update(
        version_id=version_id,
        status=final_status.value,
        builds_features_extracted=0,
        builds_total=total_builds,
        builds_ingested=ingested,
        builds_missing_resource=missing_resource,
        builds_ingestion_failed=failed,
    )

    return {
        "status": "completed",
        "final_status": final_status.value,
        "builds_ingested": ingested,
        "builds_missing_resource": missing_resource,
        "builds_ingestion_failed": failed,
        "resource_status": resource_summary,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.handle_enrichment_chord_error",
    queue="dataset_ingestion",
    soft_time_limit=60,
    time_limit=120,
)
def handle_enrichment_chord_error(
    self: PipelineTask,
    task_id: str,
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
    from celery.result import AsyncResult

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    # Try to get error info from the failed task
    error_msg = "Unknown ingestion error"
    try:
        result = AsyncResult(task_id)
        # Accessing result.result might re-raise the exception or return it
        if isinstance(result.result, Exception):
            error_msg = str(result.result)
        elif result.result:
            error_msg = str(result.result)
    except Exception as e:
        logger.warning(f"Could not retrieve exception for task {task_id}: {e}")

    logger.error(
        f"{corr_prefix} Ingestion chord failed for version {version_id}: {error_msg}"
    )

    import_build_repo = DatasetImportBuildRepository(self.db)
    version_repo = DatasetVersionRepository(self.db)

    from datetime import datetime

    now = datetime.utcnow()

    # Mark all INGESTING builds as FAILED (chord failure = actual error, retryable)
    failed_count = import_build_repo.update_many_by_status(
        version_id,
        from_status=DatasetImportBuildStatus.INGESTING.value,
        updates={
            "status": DatasetImportBuildStatus.FAILED.value,
            "ingestion_error": f"Ingestion chord failed: {error_msg}",
            "ingested_at": now,
        },
    )

    logger.warning(f"{corr_prefix} Marked {failed_count} builds as FAILED (retryable)")

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
                "builds_ingested": len(ingested_builds),
                "builds_ingestion_failed": failed_count,
            },
        )
        publish_enrichment_update(
            version_id=version_id,
            status=VersionStatus.INGESTED.value,
            builds_ingested=len(ingested_builds),
            builds_ingestion_failed=failed_count,
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
        "failed_builds": failed_count,
        "ingested_builds": len(ingested_builds) if ingested_builds else 0,
        "error": error_msg,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.reingest_failed_builds",
    queue="dataset_ingestion",
    soft_time_limit=300,
    time_limit=360,
)
def reingest_failed_builds(
    self: PipelineTask,
    version_id: str,
) -> Dict[str, Any]:
    """
    Re-ingest only FAILED import builds for a version.

    Only retries builds with status=FAILED (actual errors like timeout, network failure).
    Does NOT retry MISSING_RESOURCE builds (expected - logs expired, commit not found).
    """
    correlation_id = str(uuid.uuid4())

    version_repo = DatasetVersionRepository(self.db)
    import_build_repo = DatasetImportBuildRepository(self.db)

    # Validate version exists
    version = version_repo.find_by_id(version_id)
    if not version:
        return {"status": "error", "message": "Version not found"}

    # Find FAILED import builds (not MISSING_RESOURCE - those are not retryable)
    failed_imports = import_build_repo.find_failed_builds(version_id)
    missing_count = len(import_build_repo.find_missing_resource_imports(version_id))

    if not failed_imports:
        msg = "No failed builds to retry"
        if missing_count > 0:
            msg += f" ({missing_count} builds have missing resources - not retryable)"
        return {
            "status": "no_failed_builds",
            "failed_count": 0,
            "missing_resource_count": missing_count,
            "message": msg,
        }

    # Reset to CREATED and clear error fields
    reset_count = 0
    for build in failed_imports:
        try:
            import_build_repo.update_one(
                str(build.id),
                {
                    "status": DatasetImportBuildStatus.CREATED.value,
                    "ingestion_error": None,
                    "failed_at": None,
                },
            )
            reset_count += 1
        except Exception as e:
            logger.warning(f"Failed to reset import build {build.id}: {e}")

    if reset_count == 0:
        return {"status": "error", "message": "Failed to reset any builds"}

    start_enrichment.delay(version_id)

    logger.info(f"Re-triggered ingestion for {reset_count} failed imports")

    return {
        "status": "queued",
        "builds_reset": reset_count,
        "total_failed": len(failed_imports),
        "correlation_id": correlation_id,
    }


def _create_import_builds_for_version(
    db,
    version_id: str,
    dataset_id: str,
    required_resources: List[str],
) -> int:
    """
    Create DatasetImportBuild records for validated builds that need ingestion.

    Skip builds that already have import records with status:
    - INGESTED: Already completed
    - INGESTING: Currently processing
    - MISSING_RESOURCE: Not retryable

    Only creates records for:
    - Builds without import records (new)
    - Builds with CREATED status (waiting for ingestion)

    Args:
        db: Database connection
        version_id: DatasetVersion ID
        dataset_id: Dataset ID to get validated builds from
        required_resources: List of required resource names for ingestion

    Returns:
        Number of import build records created
    """
    from app.config import settings

    import_build_repo = DatasetImportBuildRepository(db)
    dataset_build_repo = DatasetBuildRepository(db)
    raw_build_run_repo = RawBuildRunRepository(db)
    raw_repo_repo = RawRepositoryRepository(db)

    chunk_size = settings.INGESTION_IMPORT_BUILDS_PER_CHUNK

    # Get existing import builds for this version to check duplicates
    # Use set for O(1) lookup instead of dict
    existing_imports = import_build_repo.find_by_version(version_id)
    existing_by_dataset_build = {
        str(imp.dataset_build_id): imp.status for imp in existing_imports
    }

    import_builds = []
    skipped_count = 0
    total_created = 0

    # Use paginated iterator to handle large datasets (100K+ builds)
    for batch in dataset_build_repo.iterate_validated_builds(
        dataset_id, batch_size=chunk_size
    ):
        for dataset_build in batch:
            # Skip builds without raw references
            if not dataset_build.raw_run_id or not dataset_build.raw_repo_id:
                continue

            # Check if import build already exists
            existing_status = existing_by_dataset_build.get(str(dataset_build.id))
            if existing_status:
                # Skip if already processed (INGESTED, INGESTING, MISSING_RESOURCE)
                # Only allow re-creation for CREATED (will be picked up by ingestion)
                if existing_status != DatasetImportBuildStatus.CREATED:
                    skipped_count += 1
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
                status=DatasetImportBuildStatus.CREATED,
                resource_status={},
                required_resources=required_resources,
                ci_run_id=raw_build_run.ci_run_id or "",
                commit_sha=raw_build_run.commit_sha or "",
                repo_full_name=repo_full_name,
            )
            import_builds.append(import_build)

            # Chunked bulk insert to avoid memory issues with large datasets
            if len(import_builds) >= chunk_size:
                import_build_repo.bulk_insert(import_builds)
                total_created += len(import_builds)
                logger.info(
                    f"[_create_import_builds] Inserted chunk of {len(import_builds)} builds "
                    f"(total: {total_created})"
                )
                import_builds = []

    # Insert remaining builds
    if import_builds:
        import_build_repo.bulk_insert(import_builds)
        total_created += len(import_builds)

    logger.info(
        f"[_create_import_builds] Created {total_created} import builds, "
        f"skipped {skipped_count} already processed for version {version_id}"
    )

    return total_created
