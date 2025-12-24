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
from typing import Any, Dict, List

from bson import ObjectId
from celery import chain, chord, group

from app.celery_app import celery_app
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.dataset_build import DatasetBuild
from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.entities.dataset_version import DatasetVersion
from app.entities.enums import ExtractionStatus
from app.entities.feature_audit_log import AuditLogCategory
from app.entities.raw_repository import RawRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.shared import extract_features_for_build

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
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
                "ingestion_status": "ingesting",
            },
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
            dispatch_scans_and_processing.delay(version_id, correlation_id=correlation_id)
            return {"status": "dispatched", "message": "No ingestion needed, dispatched processing"}

        # Use chord: run all repo ingestion chains in parallel → aggregate → process
        # Note: chord waits for ALL chains to complete (including retries/failures)
        workflow = chord(
            group(ingestion_chains),
            chain(
                aggregate_ingestion_results.s(version_id=version_id),
                dispatch_scans_and_processing.si(version_id=version_id),
            ),
        )
        workflow.apply_async()

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
    base=PipelineTask,
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
    Each result is from the last task in each chain (clone/worktree/logs).
    Chains may fail after retries - we count those as failed.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)

    # Domain-specific counting for ingestion status types
    repos_success = 0
    repos_failed = 0

    for result in results:
        if result is None:
            repos_failed += 1
        elif isinstance(result, dict):
            status = result.get("status", "")
            if status in ("cloned", "updated", "completed", "skipped"):
                repos_success += 1
            elif "worktrees_created" in result or "logs_downloaded" in result:
                repos_success += 1
            else:
                repos_failed += 1
        else:
            repos_failed += 1

    logger.info(
        f"{corr_prefix}[aggregate_ingestion_results] version={version_id}: "
        f"{repos_success} chains succeeded, {repos_failed} chains failed, "
        f"total results: {len(results)}"
    )

    # Update version status
    version_repo.update_one(
        version_id,
        {
            "ingestion_status": "completed",
            "ingestion_progress": 100,
            "repos_ingested": repos_success,
            "repos_failed": repos_failed,
        },
    )

    return {"success": repos_success, "failed": repos_failed}


# Task 1c: Dispatch scans and processing after ingestion
@celery_app.task(
    bind=True,
    base=PipelineTask,
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


# Task 2: Dispatch enrichment batches after ingestion
@celery_app.task(
    bind=True,
    base=PipelineTask,
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
    After ingestion completes, dispatch enrichment batches grouped by raw_repo_id.

    Uses validated repos from dataset_repo_stats for repo grouping.
    Within each repo, splits builds into chunks of ENRICHMENT_BATCH_SIZE.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    dataset_repo = DatasetRepository(self.db)
    dataset_repo_stats_repo = DatasetRepoStatsRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)

    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        raise ValueError(f"Version {version_id} not found")

    # Get validated repo IDs from dataset (set during save_repos)
    dataset = dataset_repo.find_by_id(dataset_version.dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {dataset_version.dataset_id} not found")

    # Use repo_stats to get validated repo IDs
    repo_stats_list = dataset_repo_stats_repo.find_by_dataset(str(dataset_version.dataset_id))
    validated_raw_repo_ids = [str(stat.raw_repo_id) for stat in repo_stats_list]

    if not validated_raw_repo_ids:
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No validated repos to process"}

    # Batch settings
    batch_size = settings.PROCESSING_BUILDS_PER_BATCH
    batch_tasks = []
    total_builds = 0

    # For each repo, get builds and split into batches
    for raw_repo_id in validated_raw_repo_ids:
        # Get validated builds for this repo (status='found')
        dataset_builds = dataset_build_repo.find_found_builds_by_repo(
            dataset_version.dataset_id, str(raw_repo_id)
        )
        if not dataset_builds:
            continue

        build_ids = [str(build.id) for build in dataset_builds]
        total_builds += len(build_ids)

        # Split into chunks of batch_size
        for chunk_start in range(0, len(build_ids), batch_size):
            chunk = build_ids[chunk_start : chunk_start + batch_size]
            batch_tasks.append(
                process_enrichment_batch.si(
                    version_id=version_id,
                    raw_repo_id=str(raw_repo_id),
                    validated_build_ids=chunk,
                    selected_features=dataset_version.selected_features,
                    batch_index=len(batch_tasks),
                    total_batches=0,  # Will be updated after loop
                    correlation_id=correlation_id,
                )
            )

    if not batch_tasks:
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No builds to process"}

    # Log dispatch info
    total_batches = len(batch_tasks)
    logger.info(
        f"{corr_prefix} Dispatching {total_batches} batches ({total_builds} builds) "
        f"for version {version_id}"
    )

    # Use chord to run all batches in parallel, then finalize
    chord(group(batch_tasks))(
        finalize_enrichment.s(version_id=version_id, correlation_id=correlation_id)
    )

    return {
        "status": "dispatched",
        "batches": total_batches,
        "repos": len(validated_raw_repo_ids),
        "total_builds": total_builds,
    }


# Task 2: Process batch
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.process_enrichment_batch",
    queue="processing",
    soft_time_limit=600,
    time_limit=900,
)
def process_enrichment_batch(
    self: PipelineTask,
    version_id: str,
    raw_repo_id: str,
    validated_build_ids: List[str],
    selected_features: List[str],
    batch_index: int,
    total_batches: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Process a batch of validated builds for ONE repo.

    Args:
        version_id: DatasetVersion ID
        raw_repo_id: RawRepository ID (all builds in this batch belong to this repo)
        validated_build_ids: List of DatasetBuild IDs to process
        selected_features: Features to extract
        batch_index: Current batch number
        total_batches: Total number of batches
        correlation_id: Correlation ID for tracing

    Returns stats for this batch to be aggregated by finalize_enrichment.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        return {"status": "error", "error": "Version not found"}

    # Lookup RawRepository once for this batch
    raw_repo = raw_repo_repo.find_by_id(raw_repo_id)
    if not raw_repo:
        logger.error(f"{corr_prefix} RawRepository {raw_repo_id} not found")
        return {"status": "error", "error": "RawRepository not found"}

    enriched_count = 0
    failed_count = 0

    for dataset_build_id in validated_build_ids:
        dataset_build = dataset_build_repo.find_by_id(dataset_build_id)
        if not dataset_build:
            logger.warning(f"Build {dataset_build_id} not found")
            failed_count += 1
            continue

        enrichment_build_id = None
        try:
            existing_enrichment = enrichment_build_repo.find_by_dataset_build_id(
                ObjectId(dataset_version.dataset_id), dataset_build.id
            )

            if existing_enrichment:
                enrichment_build_id = str(existing_enrichment.id)
            else:
                # Create pending build using raw_repo_id from batch params
                new_enrichment_build = DatasetEnrichmentBuild(
                    _id=None,
                    raw_repo_id=ObjectId(raw_repo_id),
                    raw_build_run_id=ObjectId(dataset_build.ci_run_id),
                    dataset_id=ObjectId(dataset_version.dataset_id),
                    dataset_version_id=ObjectId(version_id),
                    dataset_build_id=dataset_build.id,
                    extraction_status=ExtractionStatus.PENDING,
                    extraction_error=None,
                    features={},
                    enriched_at=None,
                )
                saved_enrichment = enrichment_build_repo.insert_one(new_enrichment_build)
                enrichment_build_id = str(saved_enrichment.id)

            # Extract Features using DatasetVersion for config
            extraction_result = _extract_features_for_enrichment(
                db=self.db,
                dataset_build=dataset_build,
                selected_features=selected_features,
                raw_build_run_repo=raw_build_run_repo,
                dataset_version=dataset_version,
                raw_repo=raw_repo,
            )

            # Determine extraction status from result
            if extraction_result["status"] == "completed":
                extraction_status = ExtractionStatus.COMPLETED
            elif extraction_result["status"] == "partial":
                extraction_status = ExtractionStatus.PARTIAL
            elif extraction_result["status"] == "failed":
                extraction_status = ExtractionStatus.FAILED
            else:
                extraction_status = ExtractionStatus.PENDING

            extracted_features = extraction_result["features"]
            extraction_error = (
                extraction_result["errors"][0] if extraction_result["errors"] else None
            )

            # Build update dict with Graceful Degradation tracking
            update_data = {
                "extraction_status": extraction_status,
                "extraction_error": extraction_error,
                "features": extracted_features,
                "enriched_at": datetime.now(),
            }

            # Track missing resources and skipped features
            if extraction_result.get("missing_resources"):
                update_data["missing_resources"] = extraction_result["missing_resources"]
            if extraction_result.get("skipped_features"):
                update_data["skipped_features"] = extraction_result["skipped_features"]

            enrichment_build_repo.update_one(enrichment_build_id, update_data)

            # NOTE: Scans are now dispatched in PARALLEL via dispatch_version_scans
            # called from start_enrichment, not per-build in process_enrichment_batch

            if extraction_result["status"] == "completed":
                enriched_count += 1
            else:
                failed_count += 1

        except Exception as exc:
            logger.warning(f"Failed to enrich build {dataset_build.build_id_from_csv}: {exc}")
            enrichment_build_repo.update_extraction_status(
                ObjectId(enrichment_build_id),
                ExtractionStatus.FAILED,
                error=str(exc),
            )
            failed_count += 1

    logger.info(
        f"Batch {batch_index + 1}/{total_batches} completed: "
        f"{enriched_count} enriched, {failed_count} failed"
    )

    return {
        "batch_index": batch_index,
        "status": "completed",
        "enriched": enriched_count,
        "failed": failed_count,
        "total": len(validated_build_ids),
    }


# Task 3: Finalize
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.finalize_enrichment",
    queue="processing",
    soft_time_limit=30,
    time_limit=60,
)
def finalize_enrichment(
    self: PipelineTask,
    batch_results: List[Dict[str, Any]],
    version_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Aggregate results from all batch enrichments and update version status.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)

    # Aggregate stats
    total_enriched = 0
    total_failed = 0
    total_processed = 0

    for batch_result in batch_results:
        total_enriched += batch_result.get("enriched", 0)
        total_failed += batch_result.get("failed", 0)
        total_processed += batch_result.get("total", 0)

    # Update final progress
    version_repo.update_progress(
        version_id,
        processed_rows=total_processed,
        enriched_rows=total_enriched,
        failed_rows=total_failed,
    )

    # Mark completed
    version_repo.mark_completed(version_id)

    logger.info(
        f"{corr_prefix} Version enrichment completed: {version_id}, "
        f"{total_enriched}/{total_processed} rows enriched"
    )

    return {
        "status": "completed",
        "version_id": version_id,
        "enriched_rows": total_enriched,
        "failed_rows": total_failed,
        "total_rows": total_processed,
    }


def _extract_features_for_enrichment(
    db,
    dataset_build: DatasetBuild,
    selected_features: List[str],
    raw_build_run_repo: RawBuildRunRepository,
    dataset_version: DatasetVersion,
    raw_repo: RawRepository,
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

    Returns result dict with status, features, errors, warnings.
    """
    if not dataset_build.ci_run_id:
        logger.warning(f"Build {dataset_build.build_id_from_csv} has no ci_run_id")
        return {
            "status": "failed",
            "features": {},
            "errors": ["No ci_run_id"],
            "warnings": [],
        }

    raw_build_run = raw_build_run_repo.find_by_id(str(dataset_build.ci_run_id))
    if not raw_build_run:
        logger.warning(f"RawBuildRun {dataset_build.ci_run_id} not found")
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
    )


# Task 4: Dispatch version scans (runs in parallel with ingestion)
@celery_app.task(
    bind=True,
    base=PipelineTask,
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

    from app.config import settings
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

        # Collect workflow_run_ids from this batch
        workflow_run_ids = [b.ci_run_id for b in build_batch if b.ci_run_id]
        if not workflow_run_ids:
            continue

        # Batch query RawBuildRuns for this page
        raw_build_runs = raw_build_run_repo.find_by_ids(workflow_run_ids)
        build_run_map = {str(r.id): r for r in raw_build_runs}

        # Collect unique repo IDs needed for this batch
        repo_ids_needed = set()
        for build in build_batch:
            if not build.ci_run_id:
                continue
            raw_build_run = build_run_map.get(str(build.ci_run_id))
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
            if not build.ci_run_id:
                continue
            raw_build_run = build_run_map.get(str(build.ci_run_id))
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
    from datetime import datetime, timezone

    from app.config import settings
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
