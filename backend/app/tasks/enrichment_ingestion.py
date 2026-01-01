"""
Version Enrichment Ingestion Tasks - Phase 1: Clone, Worktree, Logs.

This module handles the ingestion phase of dataset version enrichment:
1. start_enrichment - Orchestrator: Build parallel ingestion tasks
2. aggregate_ingestion_results - Chord callback: aggregate ingestion results
3. handle_enrichment_chord_error - Error handler for ingestion failures
4. dispatch_version_scans - Dispatch scans per unique commit (async)
5. reingest_failed_builds - Retry FAILED builds (not MISSING_RESOURCE)

After ingestion completes, user triggers Phase 2 (processing) via
start_enrichment_processing in enrichment_processing.py.
"""

import json
import logging
import uuid
from typing import Any, Dict, List

from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.core.tracing import TracingContext
from app.entities.dataset_build import DatasetBuild
from app.entities.dataset_import_build import (
    DatasetImportBuild,
    DatasetImportBuildStatus,
    ResourceStatus,
)
from app.entities.dataset_version import VersionStatus
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_import_build import DatasetImportBuildRepository
from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import EnrichmentTask, PipelineTask
from app.tasks.pipeline.shared.resources import FeatureResource
from app.tasks.shared.events import publish_enrichment_update

logger = logging.getLogger(__name__)


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
                    aggregate_ingestion_results
                )

    After ingestion completes, version is marked as INGESTED.
    User triggers processing (Phase 2) manually via start_enrichment_processing.

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
        validated_builds = dataset_build_repo.find_validated_builds(str(dataset_version.dataset_id))

        builds_total = len(validated_builds)
        if builds_total == 0:
            raise ValueError("No validated builds found. Please run validation first.")

        # Get validated repos from dataset stats
        repo_stats_list = dataset_repo_stats_repo.find_by_dataset(str(dataset_version.dataset_id))
        validated_raw_repo_ids = [str(stat.raw_repo_id) for stat in repo_stats_list]

        version_repo.update_one(
            version_id,
            {
                "builds_total": builds_total,
                "status": VersionStatus.INGESTING.value,
            },
        )
        # Publish initial progress via WebSocket
        publish_enrichment_update(
            version_id=version_id,
            status="ingesting",
            builds_processed=0,
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
                str(dataset_version.dataset_id), raw_repo_id
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
            logger.info("[start_enrichment] No ingestion chains needed, marking as ingested")
            # Mark import builds as INGESTED since no ingestion is needed
            import_build_repo = DatasetImportBuildRepository(self.db)
            import_build_repo.mark_ingested_batch(version_id)

            # Mark version as INGESTED - user triggers processing manually
            version_repo.update_one(
                version_id,
                {
                    "status": VersionStatus.INGESTED.value,
                    "ingestion_progress": 100,
                },
            )
            publish_enrichment_update(
                version_id=version_id,
                status=VersionStatus.INGESTED.value,
                builds_processed=0,
                builds_total=builds_total,
            )
            return {
                "status": "completed",
                "message": "Ingestion complete. Start processing when ready.",
            }

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
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    import_build_repo = DatasetImportBuildRepository(self.db)

    # Fetch and normalize results from Redis or arguments (same pattern as model_ingestion)
    all_results = _fetch_and_parse_results(self.redis, correlation_id, results, corr_prefix)

    # Collect failed items from task results
    clone_failed = False
    clone_error = None
    failed_commits: list[str] = []
    created_commits: list[str] = []
    failed_log_ids: list[str] = []
    expired_log_ids: list[str] = []
    downloaded_log_ids: list[str] = []
    skipped_log_ids: list[str] = []

    for r in all_results:
        if not isinstance(r, dict):
            continue
        # Check clone result (git_history) - affects ALL builds
        if r.get("resource") == FeatureResource.GIT_HISTORY.value and r.get("status") in (
            "timeout",
            "failed",
        ):
            clone_failed = True
            clone_error = r.get("error")

        # Collect failed and created commits from worktree chunks
        if r.get("resource") == FeatureResource.GIT_WORKTREE.value:
            if "failed_commits" in r:
                failed_commits.extend(r["failed_commits"])
            if "created_commits" in r:
                created_commits.extend(r["created_commits"])

        # Collect log IDs from log chunks
        if r.get("resource") == FeatureResource.BUILD_LOGS.value:
            if "failed_log_ids" in r:
                failed_log_ids.extend(r["failed_log_ids"])
            if "expired_log_ids" in r:
                expired_log_ids.extend(r["expired_log_ids"])
            if "downloaded_log_ids" in r:
                downloaded_log_ids.extend(r["downloaded_log_ids"])
            if "skipped_log_ids" in r:
                skipped_log_ids.extend(r["skipped_log_ids"])

    # Cleanup Redis key
    if correlation_id:
        try:
            self.redis.delete(f"ingestion:results:{correlation_id}")
        except Exception as e:
            logger.warning(f"{corr_prefix} Failed to cleanup Redis key: {e}")

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
        wt_key = f"resource_status.{FeatureResource.GIT_WORKTREE.value}"
        import_build_repo.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "commit_sha": {"$in": failed_commits},
            },
            {
                "$set": {
                    f"{wt_key}.status": ResourceStatus.FAILED.value,
                    f"{wt_key}.error": "Worktree creation failed",
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
        log_key = f"resource_status.{FeatureResource.BUILD_LOGS.value}"
        import_build_repo.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "ci_run_id": {"$in": all_failed_logs},
            },
            {
                "$set": {
                    f"{log_key}.status": ResourceStatus.FAILED.value,
                    f"{log_key}.error": "Log download failed or expired",
                }
            },
        )
    # Mark remaining as completed
    import_build_repo.update_resource_status_batch(
        version_id, FeatureResource.BUILD_LOGS.value, ResourceStatus.COMPLETED
    )

    # === Determine per-build final status ===
    # FAILED: Actual error (timeout, network, exception) - RETRYABLE
    # MISSING_RESOURCE: Expected (logs expired, commit not in repo) - NOT RETRYABLE

    from datetime import datetime

    now = datetime.utcnow()

    # Mark builds as FAILED if clone failed (all builds) - this is an actual error
    if clone_failed:
        import_build_repo.update_many_by_status(
            version_id,
            from_status=DatasetImportBuildStatus.INGESTING.value,
            updates={
                "status": DatasetImportBuildStatus.FAILED.value,
                "ingestion_error": clone_error or "Clone failed",
                "failed_at": now,
            },
        )
    else:
        # Mark builds with failed worktrees as FAILED (actual error - retryable)
        if failed_commits:
            import_build_repo.collection.update_many(
                {
                    "dataset_version_id": ObjectId(version_id),
                    "status": DatasetImportBuildStatus.INGESTING.value,
                    "commit_sha": {"$in": failed_commits},
                },
                {
                    "$set": {
                        "status": DatasetImportBuildStatus.FAILED.value,
                        "ingestion_error": "Worktree creation failed",
                        "failed_at": now,
                    }
                },
            )

        # Mark builds with failed logs as FAILED (actual error - retryable)
        if failed_log_ids:
            import_build_repo.collection.update_many(
                {
                    "dataset_version_id": ObjectId(version_id),
                    "status": DatasetImportBuildStatus.INGESTING.value,
                    "ci_run_id": {"$in": failed_log_ids},
                },
                {
                    "$set": {
                        "status": DatasetImportBuildStatus.FAILED.value,
                        "ingestion_error": "Log download failed",
                        "failed_at": now,
                    }
                },
            )

        # Mark builds with expired logs as MISSING_RESOURCE (expected - not retryable)
        if expired_log_ids:
            import_build_repo.collection.update_many(
                {
                    "dataset_version_id": ObjectId(version_id),
                    "status": DatasetImportBuildStatus.INGESTING.value,
                    "ci_run_id": {"$in": expired_log_ids},
                },
                {
                    "$set": {
                        "status": DatasetImportBuildStatus.MISSING_RESOURCE.value,
                        "ingestion_error": "Logs expired",
                        "failed_at": now,
                    }
                },
            )

        # Mark remaining INGESTING builds as INGESTED
        import_build_repo.mark_ingested_batch(version_id)

    # Count by status to determine final state
    status_counts = import_build_repo.count_by_status(version_id)
    ingested = status_counts.get(DatasetImportBuildStatus.INGESTED.value, 0)
    missing_resource = status_counts.get(DatasetImportBuildStatus.MISSING_RESOURCE.value, 0)
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
        msg = f"Ingestion complete: {ingested} builds ready. Start processing when ready."

    total_builds = ingested + missing_resource + failed
    version_repo.update_one(
        version_id,
        {
            "status": final_status.value,
            "ingestion_progress": 100,
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
        builds_processed=0,
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

    from datetime import datetime

    now = datetime.utcnow()

    # Mark all INGESTING builds as FAILED (chord failure = actual error, retryable)
    failed_count = import_build_repo.update_many_by_status(
        version_id,
        from_status=DatasetImportBuildStatus.INGESTING.value,
        updates={
            "status": DatasetImportBuildStatus.FAILED.value,
            "ingestion_error": f"Ingestion chord failed: {error_msg}",
            "failed_at": now,
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
    base=EnrichmentTask,
    name="app.tasks.version_enrichment.reingest_failed_builds",
    queue="processing",
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

    # Reset to PENDING and clear error fields
    reset_count = 0
    for build in failed_imports:
        try:
            import_build_repo.update_one(
                str(build.id),
                {
                    "status": DatasetImportBuildStatus.PENDING.value,
                    "ingestion_error": None,
                    "failed_at": None,
                },
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


def _fetch_and_parse_results(
    redis_client,
    correlation_id: str,
    fallback_results: Any,
    log_prefix: str,
) -> List[Dict[str, Any]]:
    """Fetch results from Redis or use fallback (same pattern as model_ingestion)."""
    all_results = []

    if correlation_id:
        try:
            key = f"ingestion:results:{correlation_id}"
            redis_results: List[bytes] = redis_client.lrange(key, 0, -1)  # type: ignore[assignment]
            if redis_results:
                logger.info(f"{log_prefix} Fetched {len(redis_results)} results from Redis")
                for r_str in redis_results:
                    try:
                        all_results.append(json.loads(r_str))
                    except Exception as e:
                        logger.warning(f"{log_prefix} Failed to decode Redis result: {e}")
        except Exception as e:
            logger.error(f"{log_prefix} Error fetching results from Redis: {e}")

    if not all_results:
        if isinstance(fallback_results, list):
            all_results = fallback_results
        elif isinstance(fallback_results, dict):
            all_results = [fallback_results]
        logger.info(f"{log_prefix} Used {len(all_results)} results from task arguments")

    return all_results
