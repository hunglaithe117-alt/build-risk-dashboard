"""
Dataset Validation Tasks - Distributed validation using MapReduce pattern.

This module implements scalable validation for large CSV files (3M+ records):

Tasks:
1. dataset_validation_orchestrator - Main entry, reads CSV chunks, dispatches workers
2. validate_repo_chunk - Validates batch of repos via GitHub API
3. validate_builds_chunk - Validates batch of builds via CI API
4. aggregate_validation_results - Collects results and updates dataset

Architecture:
    Orchestrator
        ├── Repo Chunk 1 → Build Chunks 1.1, 1.2, ...
        ├── Repo Chunk 2 → Build Chunks 2.1, 2.2, ...
        └── Repo Chunk N → Build Chunks N.1, N.2, ...
                              ↓
                        Aggregator (chord callback)
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from bson import ObjectId
from celery import chain, group

from app.celery_app import celery_app
from app.ci_providers.factory import get_ci_provider
from app.ci_providers.models import BuildData, CIProvider
from app.config import settings
from app.core.tracing import TracingContext
from app.database.mongo import get_database
from app.entities import DatasetBuild, DatasetBuildStatus, ValidationStats
from app.entities.dataset import DatasetValidationStatus
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.github.github_client import get_public_github_client
from app.tasks.base import PipelineTask
from app.tasks.dataset_validation_helpers import (
    batch_create_dataset_builds,
    calculate_progress,
    chunk_dict,
    chunk_list,
    cleanup_validation_stats,
    get_validation_stats,
    group_builds_by_repo,
    increment_validation_stat,
    init_validation_stats,
    is_validation_cancelled,
    read_csv_chunks,
)
from app.utils.datetime import utc_now

logger = logging.getLogger(__name__)


def publish_dataset_update(
    dataset_id: str,
    status: str,
    progress: int = 0,
    stats: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
):
    """Publish dataset validation update to Redis for WebSocket broadcast."""
    import json

    import redis

    try:
        r = redis.from_url(settings.REDIS_URL)
        payload = {
            "type": "DATASET_UPDATE",
            "payload": {
                "dataset_id": dataset_id,
                "validation_status": status,
                "validation_progress": progress,
            },
        }
        if stats:
            payload["payload"]["validation_stats"] = stats
        if error:
            payload["payload"]["validation_error"] = error

        r.publish("events", json.dumps(payload))
    except Exception as e:
        logger.error(f"Failed to publish dataset update: {e}")


# =============================================================================
# Task 1: Orchestrator
# =============================================================================


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_validation.dataset_validation_orchestrator",
    queue="validation",
    soft_time_limit=3600,
    time_limit=3660,
)
def dataset_validation_orchestrator(self, dataset_id: str) -> Dict[str, Any]:
    """
    Orchestrator task for distributed dataset validation.

    Reads CSV in chunks, groups by repo, and dispatches worker tasks.
    Uses Celery chord to aggregate results after all workers complete.

    Args:
        dataset_id: ID of the dataset to validate

    Returns:
        Dict with dispatch status
    """
    # Generate correlation_id for entire validation run
    correlation_id = str(uuid.uuid4())
    corr_prefix = f"[corr={correlation_id[:8]}]"

    # Set tracing context for structured logging
    TracingContext.set(
        correlation_id=correlation_id,
        dataset_id=dataset_id,
        pipeline_type="dataset_validation",
    )

    db = get_database()
    dataset_repo = DatasetRepository(db)

    try:
        logger.info(f"{corr_prefix}[dataset_validation] Starting for dataset {dataset_id}")

        # Load dataset
        dataset = dataset_repo.find_by_id(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Mark validation started
        dataset_repo.update_one(
            dataset_id,
            {
                "validation_status": DatasetValidationStatus.VALIDATING,
                "validation_started_at": utc_now(),
                "validation_task_id": self.request.id,
                "validation_progress": 0,
                "validation_error": None,
            },
        )
        publish_dataset_update(dataset_id, "validating", progress=0)

        # Get configuration
        file_path = dataset.file_path
        build_id_column = dataset.mapped_fields.build_id
        repo_name_column = dataset.mapped_fields.repo_name
        ci_provider_column = dataset.mapped_fields.ci_provider
        single_ci_provider = (
            (
                dataset.ci_provider.value
                if hasattr(dataset.ci_provider, "value")
                else dataset.ci_provider
            )
            if dataset.ci_provider
            else None
        )

        if not build_id_column or not repo_name_column:
            raise ValueError("Dataset column mapping not configured")

        # Read CSV in chunks and aggregate all builds
        logger.info(f"Reading CSV in chunks from {file_path}")
        all_repo_builds: Dict[str, List[Dict[str, str]]] = {}

        for chunk_df in read_csv_chunks(
            file_path=file_path,
            build_id_column=build_id_column,
            repo_name_column=repo_name_column,
            ci_provider_column=ci_provider_column,
            single_ci_provider=single_ci_provider,
        ):
            chunk_repo_builds = group_builds_by_repo(chunk_df)
            for repo_name, builds in chunk_repo_builds.items():
                if repo_name not in all_repo_builds:
                    all_repo_builds[repo_name] = []
                all_repo_builds[repo_name].extend(builds)

        # Resume logic: Skip already validated builds
        dataset_build_repo = DatasetBuildRepository(db)
        validated_builds = {
            b.build_id_from_csv
            for b in dataset_build_repo.find_many({"dataset_id": ObjectId(dataset_id)})
            if b.build_id_from_csv
        }

        if validated_builds:
            logger.info(f"Resuming: skipping {len(validated_builds)} already validated builds")
            for repo_name in list(all_repo_builds.keys()):
                remaining = [
                    b for b in all_repo_builds[repo_name] if b["build_id"] not in validated_builds
                ]
                if remaining:
                    all_repo_builds[repo_name] = remaining
                else:
                    del all_repo_builds[repo_name]

        total_repos = len(all_repo_builds)
        total_builds = sum(len(builds) for builds in all_repo_builds.values())

        logger.info(f"Found {total_repos} repos, {total_builds} builds to validate")

        if total_repos == 0:
            dataset_repo.update_one(
                dataset_id,
                {
                    "validation_status": DatasetValidationStatus.COMPLETED,
                    "validation_completed_at": utc_now(),
                    "validation_progress": 100,
                    "setup_step": 2,
                },
            )
            publish_dataset_update(dataset_id, "completed", progress=100)
            return {"status": "completed", "message": "No valid repos found"}

        # Initialize Redis counters
        init_validation_stats(dataset_id, total_repos, total_builds)

        # Chunk repos for parallel processing
        repo_chunks = list(chunk_dict(all_repo_builds, settings.VALIDATION_REPOS_PER_TASK))

        # Update total chunks in Redis
        increment_validation_stat(dataset_id, "total_chunks", len(repo_chunks))

        repo_tasks = [
            validate_repo_chunk.si(
                dataset_id=dataset_id,
                repo_builds_chunk=chunk,
                chunk_index=i,
                correlation_id=correlation_id,
            )
            for i, chunk in enumerate(repo_chunks)
        ]

        build_tasks = []
        for repo_name, builds in all_repo_builds.items():
            build_chunks = list(chunk_list(builds, settings.VALIDATION_BUILDS_PER_TASK))
            for build_chunk in build_chunks:
                build_tasks.append(
                    validate_builds_chunk.si(
                        dataset_id=dataset_id,
                        repo_name=repo_name,
                        raw_repo_id=None,  # Will be looked up in task
                        builds=build_chunk,
                        correlation_id=correlation_id,
                    )
                )

        # Two-stage workflow:
        # Stage 1: All repo validation tasks
        # Stage 2: All build validation tasks
        # Final: Aggregate results
        workflow = chain(
            group(repo_tasks),  # Stage 1: Validate repos first
            group(build_tasks),  # Stage 2: Validate builds
            aggregate_validation_results.si(
                dataset_id=dataset_id, correlation_id=correlation_id
            ),  # Final: Aggregate results
        ).apply_async()

        logger.info(
            f"{corr_prefix}[dataset_validation] Dispatched {len(repo_chunks)} repo chunks, "
            f"workflow_id={workflow.id}"
        )

        return {
            "status": "dispatched",
            "total_repos": total_repos,
            "total_builds": total_builds,
            "chunks": len(repo_chunks),
            "workflow_id": str(workflow.id),
            "correlation_id": correlation_id,
        }

    except Exception as e:
        logger.exception(f"{corr_prefix}[dataset_validation] Orchestrator failed: {e}")
        dataset_repo.update_one(
            dataset_id,
            {
                "validation_status": DatasetValidationStatus.FAILED,
                "validation_completed_at": utc_now(),
                "validation_error": str(e),
                "correlation_id": correlation_id,
            },
        )
        publish_dataset_update(dataset_id, "failed", error=str(e))
        raise


# Task 2: Repo Chunk Validator
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_validation.validate_repo_chunk",
    queue="validation",
    soft_time_limit=600,
    time_limit=660,
)
def validate_repo_chunk(
    self,
    dataset_id: str,
    repo_builds_chunk: Dict[str, List[Dict[str, str]]],
    chunk_index: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Validate a chunk of repositories and dispatch build validation tasks.

    Args:
        dataset_id: Dataset being validated
        repo_builds_chunk: Dict mapping repo_name to build list
        chunk_index: Index of this chunk
        correlation_id: Correlation ID for tracing

    Returns:
        Dict with validation results for this chunk
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[validate_repo_chunk][chunk={chunk_index}]"
    db = get_database()
    raw_repo_repo = RawRepositoryRepository(db)
    dataset_repo_stats_repo = DatasetRepoStatsRepository(db)

    # Check if cancelled before starting
    if is_validation_cancelled(dataset_id):
        logger.info(f"{log_ctx} Validation cancelled, skipping chunk")
        return {"chunk_index": chunk_index, "cancelled": True, "correlation_id": correlation_id}

    repos_valid = 0
    repos_not_found = 0
    repos_private = 0
    valid_repos_data: List[Dict[str, Any]] = []

    with get_public_github_client() as client:
        for repo_name, builds in repo_builds_chunk.items():
            # Check cancellation periodically
            if is_validation_cancelled(dataset_id):
                logger.info(f"Validation cancelled mid-chunk for {dataset_id}")
                break
            try:
                # Check repo exists using shared client
                repo_data = client.get_repository(repo_name)

                # Check if private
                if repo_data.get("private"):
                    repos_private += 1
                    increment_validation_stat(dataset_id, "repos_private")
                    increment_validation_stat(dataset_id, "builds_not_found", len(builds))
                    continue

                # Create/update RawRepository
                raw_repo = raw_repo_repo.upsert_by_full_name(
                    full_name=repo_name,
                    github_repo_id=repo_data.get("id"),
                    default_branch=repo_data.get("default_branch", "main"),
                    is_private=False,
                    main_lang=repo_data.get("language"),
                    github_metadata=repo_data,
                )

                repos_valid += 1
                increment_validation_stat(dataset_id, "repos_valid")

                # Extract CI provider from first build
                # All builds for same repo have same ci_provider
                ci_provider = builds[0].get("ci_provider") if builds else None

                dataset_repo_stats_repo.upsert_by_dataset_and_repo(
                    dataset_id=dataset_id,
                    raw_repo_id=str(raw_repo.id),
                    full_name=repo_name,
                    ci_provider=ci_provider or "github_actions",
                )

                valid_repos_data.append(
                    {
                        "repo_name": repo_name,
                        "raw_repo_id": str(raw_repo.id),
                        "builds": builds,
                    }
                )

            except Exception as e:
                # Handle status errors (404 etc wrapped in exceptions) or other failures
                # Determine if it's a 404 (Not Found)
                is_not_found = "404" in str(e) or "Not Found" in str(e)

                if is_not_found:
                    logger.warning(f"Repo not found {repo_name}: {e}")
                else:
                    logger.error(f"Failed to validate repo {repo_name}: {e}")

                repos_not_found += 1
                increment_validation_stat(dataset_id, "repos_not_found")
                increment_validation_stat(dataset_id, "builds_not_found", len(builds))

    # Update chunk completion
    increment_validation_stat(dataset_id, "chunks_completed")

    # Publish progress update
    stats = get_validation_stats(dataset_id)
    progress = calculate_progress(stats["chunks_completed"], stats["total_chunks"])
    publish_dataset_update(dataset_id, "validating", progress=progress, stats=stats)

    return {
        "chunk_index": chunk_index,
        "repos_valid": repos_valid,
        "repos_not_found": repos_not_found,
        "repos_private": repos_private,
        "correlation_id": correlation_id,
    }


# Task 3: Build Chunk Validator
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_validation.validate_builds_chunk",
    queue="validation",
    soft_time_limit=300,
    time_limit=360,
)
def validate_builds_chunk(
    self,
    dataset_id: str,
    repo_name: str,
    raw_repo_id: str,
    builds: List[Dict[str, str]],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Validate a chunk of builds for a single repository.

    Uses concurrent async requests for faster validation.

    Args:
        dataset_id: Dataset being validated
        repo_name: Repository full name
        raw_repo_id: RawRepository ObjectId string
        builds: List of build info dicts
        correlation_id: Correlation ID for tracing

    Returns:
        Dict with validation results
    """
    import asyncio

    db = get_database()
    dataset_build_repo = DatasetBuildRepository(db)
    raw_build_run_repo = RawBuildRunRepository(db)
    raw_repo_repo = RawRepositoryRepository(db)

    # Check if cancelled before starting
    if is_validation_cancelled(dataset_id):
        return {"repo_name": repo_name, "cancelled": True, "correlation_id": correlation_id}

    # Lookup raw_repo_id if not provided (dispatched from orchestrator)
    if raw_repo_id is None:
        raw_repo = raw_repo_repo.find_by_full_name(repo_name)
        if raw_repo:
            raw_repo_id = str(raw_repo.id)
        else:
            # Repo not validated yet or not found - skip builds
            logger.warning(f"RawRepository not found for {repo_name}, skipping build validation")
            return {
                "repo_name": repo_name,
                "builds_found": 0,
                "builds_not_found": len(builds),
                "skipped": True,
                "correlation_id": correlation_id,
            }

    builds_found = 0
    builds_not_found = 0
    builds_filtered = 0
    builds_to_insert: List[DatasetBuild] = []

    # Determine CI provider from first build
    ci_provider_str = builds[0].get("ci_provider", "github_actions") if builds else "github_actions"
    ci_provider = CIProvider(ci_provider_str)

    # Get CI provider client
    ci_client = get_ci_provider(ci_provider, db=db)

    # Load build filters from dataset
    dataset_repo = DatasetRepository(db)
    dataset = dataset_repo.find_by_id(dataset_id)
    build_filters = getattr(dataset, "build_filters", None)
    if build_filters is None:
        # Default filters
        exclude_bots = False
        only_completed = True
        allowed_conclusions = ["success", "failure"]
    else:
        exclude_bots = getattr(build_filters, "exclude_bots", False)
        only_completed = getattr(build_filters, "only_completed", True)
        allowed_conclusions = getattr(build_filters, "allowed_conclusions", ["success", "failure"])

    build_ids = [b["build_id"] for b in builds]
    existing_builds = dataset_build_repo.find_many(
        {
            "dataset_id": ObjectId(dataset_id),
            "raw_repo_id": ObjectId(raw_repo_id),
            "build_id_from_csv": {"$in": build_ids},
        }
    )
    existing_map = {b.build_id_from_csv: b for b in existing_builds}

    # Filter out already validated builds
    builds_to_validate = []
    for build_info in builds:
        build_id = build_info["build_id"]
        existing = existing_map.get(build_id)
        if existing:
            if existing.status == DatasetBuildStatus.FOUND:
                builds_found += 1
            else:
                builds_not_found += 1
        else:
            builds_to_validate.append(build_info)

    # Fetch all build details concurrently
    async def fetch_build_details_batch() -> List[Optional[BuildData]]:
        """Fetch all build data concurrently using fetch_build_details."""
        tasks = []
        for build_info in builds_to_validate:
            build_id = build_info["build_id"]
            formatted_build_id = f"{repo_name}:{build_id}"
            tasks.append(ci_client.fetch_build_details(formatted_build_id))
        return await asyncio.gather(*tasks, return_exceptions=True)

    # Run async fetching
    try:
        build_results = asyncio.run(fetch_build_details_batch())
    except Exception as e:
        logger.error(f"Failed to fetch build details for {repo_name}: {e}")
        build_results = [e] * len(builds_to_validate)

    # Helper to check if build should be filtered
    def should_filter_build(build_data: BuildData) -> tuple[bool, str]:
        """Check if build should be filtered based on dataset filters."""
        conclusion = (
            build_data.conclusion.value
            if hasattr(build_data.conclusion, "value")
            else build_data.conclusion
        )

        # Check only_completed filter
        if only_completed and not ci_client.is_build_completed(build_data):
            return True, "Build not completed"

        # Check exclude_bots filter
        if exclude_bots and getattr(build_data, "is_bot_commit", False):
            return True, "Bot commit"

        # Check if conclusion is in allowed list
        if conclusion not in allowed_conclusions:
            return True, f"Conclusion '{conclusion}' not in allowed list"

        return False, ""

    # Process results
    for build_info, build_data in zip(builds_to_validate, build_results, strict=False):
        build_id = build_info["build_id"]

        # Check cancellation periodically
        if is_validation_cancelled(dataset_id):
            break

        try:
            # Handle fetch errors
            if isinstance(build_data, Exception):
                raise build_data

            if build_data:
                raw_build_run = raw_build_run_repo.upsert_by_business_key(
                    raw_repo_id=ObjectId(raw_repo_id),
                    build_id=build_id,
                    provider=ci_provider,
                    repo_name=build_data.repo_name or repo_name,
                    build_number=build_data.build_number,
                    status=build_data.status.value
                    if hasattr(build_data.status, "value")
                    else build_data.status,
                    conclusion=build_data.conclusion.value
                    if hasattr(build_data.conclusion, "value")
                    else build_data.conclusion,
                    commit_sha=build_data.commit_sha,
                    branch=build_data.branch,
                    started_at=build_data.started_at,
                    completed_at=build_data.completed_at,
                    duration_seconds=build_data.duration_seconds,
                    web_url=build_data.web_url,
                    raw_data=build_data.raw_data,
                )

                # Check if build should be filtered for dataset
                should_filter, filter_reason = should_filter_build(build_data)
                if should_filter:
                    builds_filtered += 1
                    builds_to_insert.append(
                        DatasetBuild(
                            _id=None,
                            dataset_id=ObjectId(dataset_id),
                            build_id_from_csv=build_id,
                            repo_name_from_csv=repo_name,
                            raw_repo_id=ObjectId(raw_repo_id),
                            status=DatasetBuildStatus.FILTERED,
                            raw_run_id=raw_build_run.id,  # Reference to RawBuildRun
                            validation_error=f"Filtered: {filter_reason}",
                            validated_at=utc_now(),
                        )
                    )
                else:
                    # Build passed filters
                    builds_to_insert.append(
                        DatasetBuild(
                            _id=None,
                            dataset_id=ObjectId(dataset_id),
                            build_id_from_csv=build_id,
                            repo_name_from_csv=repo_name,
                            raw_repo_id=ObjectId(raw_repo_id),
                            status=DatasetBuildStatus.FOUND,
                            raw_run_id=raw_build_run.id,
                            validated_at=utc_now(),
                        )
                    )
                    builds_found += 1

            else:
                builds_to_insert.append(
                    DatasetBuild(
                        _id=None,
                        dataset_id=ObjectId(dataset_id),
                        build_id_from_csv=build_id,
                        repo_name_from_csv=repo_name,
                        raw_repo_id=ObjectId(raw_repo_id),
                        status=DatasetBuildStatus.NOT_FOUND,
                        validation_error="Build not found or incomplete",
                        validated_at=utc_now(),
                    )
                )
                builds_not_found += 1

        except Exception as e:
            logger.warning(f"Build validation error {repo_name}/{build_id}: {e}")
            builds_to_insert.append(
                DatasetBuild(
                    _id=None,
                    dataset_id=ObjectId(dataset_id),
                    build_id_from_csv=build_id,
                    repo_name_from_csv=repo_name,
                    raw_repo_id=ObjectId(raw_repo_id),
                    status=DatasetBuildStatus.ERROR,
                    validation_error=str(e),
                    validated_at=utc_now(),
                )
            )
            builds_not_found += 1

    # Batch insert all builds
    if builds_to_insert:
        batch_create_dataset_builds(dataset_build_repo, builds_to_insert)

    # Update Redis counters
    increment_validation_stat(dataset_id, "builds_found", builds_found)
    increment_validation_stat(dataset_id, "builds_not_found", builds_not_found)
    increment_validation_stat(dataset_id, "builds_filtered", builds_filtered)

    return {
        "repo_name": repo_name,
        "builds_found": builds_found,
        "builds_not_found": builds_not_found,
        "builds_filtered": builds_filtered,
        "correlation_id": correlation_id,
    }


# Task 4: Result Aggregator
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_validation.aggregate_validation_results",
    queue="validation",
    soft_time_limit=300,
    time_limit=360,
)
def aggregate_validation_results(
    self,
    dataset_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Aggregate validation results from all worker tasks.

    Called as final step in chain after:
    1. Repo validation group (creates RawRepository records)
    2. Build validation group (validates builds, creates RawBuildRun records)

    Args:
        dataset_id: Dataset that was validated
        correlation_id: Correlation ID for tracing

    Returns:
        Final validation summary
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[aggregate_results][dataset={dataset_id}]"

    # Set tracing context for logging
    if correlation_id:
        TracingContext.set(
            correlation_id=correlation_id,
            dataset_id=dataset_id,
            pipeline_type="dataset_validation",
        )

    db = get_database()
    dataset_repo = DatasetRepository(db)
    dataset_build_repo = DatasetBuildRepository(db)
    dataset_repo_stats_repo = DatasetRepoStatsRepository(db)

    # Get final stats from Redis (all tasks have completed at this point)
    stats = get_validation_stats(dataset_id)

    total_repos = stats["total_repos"]
    total_builds = stats["total_builds"]
    repos_valid = stats["repos_valid"]
    repos_not_found = stats["repos_not_found"] + stats["repos_private"]
    builds_found = stats["builds_found"]
    builds_not_found = stats["builds_not_found"]
    builds_filtered = stats["builds_filtered"]

    # Calculate coverage
    build_coverage = round((builds_found / total_builds) * 100, 2) if total_builds > 0 else 0.0

    try:
        # Aggregate builds by repo_name_from_csv
        pipeline = [
            {"$match": {"dataset_id": ObjectId(dataset_id)}},
            {
                "$group": {
                    "_id": "$repo_name_from_csv",
                    "raw_repo_id": {"$first": "$raw_repo_id"},
                    "builds_total": {"$sum": 1},
                    "builds_found": {"$sum": {"$cond": [{"$eq": ["$status", "found"]}, 1, 0]}},
                    "builds_not_found": {
                        "$sum": {"$cond": [{"$eq": ["$status", "not_found"]}, 1, 0]}
                    },
                    "builds_filtered": {
                        "$sum": {"$cond": [{"$eq": ["$status", "filtered"]}, 1, 0]}
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]
        agg_results = list(dataset_build_repo.collection.aggregate(pipeline))

        for agg in agg_results:
            full_name = agg["_id"]
            raw_repo_id = agg["raw_repo_id"]

            # Update stats in DatasetRepoStats collection
            if raw_repo_id:
                dataset_repo_stats_repo.upsert_by_dataset_and_repo(
                    dataset_id=dataset_id,
                    raw_repo_id=str(raw_repo_id),
                    full_name=full_name,
                    builds_total=agg["builds_total"],
                    builds_found=agg["builds_found"],
                    builds_not_found=agg["builds_not_found"],
                    builds_filtered=agg["builds_filtered"],
                    is_valid=agg["builds_found"] > 0,
                )
    except Exception as e:
        logger.warning(f"{log_ctx} Failed to aggregate per-repo stats: {e}")
        raise

    # Build final stats
    final_stats = ValidationStats(
        repos_total=total_repos,
        repos_valid=repos_valid,
        repos_not_found=repos_not_found,
        repos_invalid=0,
        builds_total=total_builds,
        builds_found=builds_found,
        builds_not_found=builds_not_found,
        builds_filtered=builds_filtered,
    )

    # Update dataset
    dataset_repo.update_one(
        dataset_id,
        {
            "validation_status": DatasetValidationStatus.COMPLETED,
            "validation_completed_at": utc_now(),
            "validation_progress": 100,
            "validation_stats": final_stats.model_dump(),
            "stats.build_coverage": build_coverage,
            "setup_step": 2,
        },
    )

    # Publish completion
    publish_dataset_update(
        dataset_id,
        "completed",
        progress=100,
        stats=final_stats.model_dump(),
    )

    # Cleanup Redis
    cleanup_validation_stats(dataset_id)

    logger.info(
        f"Dataset validation completed: {dataset_id}, "
        f"{repos_valid}/{total_repos} repos, {builds_found}/{total_builds} builds"
    )

    return {
        "status": "completed",
        "dataset_id": dataset_id,
        "stats": final_stats.model_dump(),
        "build_coverage": build_coverage,
        "correlation_id": correlation_id,
    }
