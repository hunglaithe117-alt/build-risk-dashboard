"""
Source Validation Tasks - Distributed validation using MapReduce pattern.

Similar to dataset_validation.py but uses BuildSource entities.
Creates raw_build_runs from CSV data via CI provider validation.

Tasks:
1. source_validation_orchestrator - Main entry, reads CSV chunks, dispatches workers
2. validate_source_repo_chunk - Validates batch of repos via GitHub API
3. validate_source_builds_chunk - Validates batch of builds via CI API
4. aggregate_source_validation_results - Collects results and updates source

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
from typing import Any, Callable, Dict, List, Optional

import redis
from bson import ObjectId
from celery import chain, group

from app.celery_app import celery_app
from app.ci_providers.config import get_provider_config
from app.ci_providers.factory import get_ci_provider
from app.ci_providers.models import BuildData, CIProvider
from app.config import settings
from app.core.tracing import TracingContext
from app.database.mongo import get_database
from app.entities.build_source import ValidationStats, ValidationStatus
from app.entities.source_build import SourceBuild, SourceBuildStatus
from app.repositories.build_source import BuildSourceRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.repositories.source_build import SourceBuildRepository
from app.repositories.source_repo_stats import SourceRepoStatsRepository
from app.services.github.github_client import get_public_github_client
from app.tasks.base import SafeTask
from app.tasks.validation_helpers import (
    calculate_progress,
    chunk_dict,
    chunk_list,
    cleanup_validation_stats,
    get_validation_stats,
    group_builds_by_repo,
    increment_validation_stat,
    init_validation_stats,
    read_csv_chunks,
)
from app.utils.datetime import utc_now

logger = logging.getLogger(__name__)


class SourceValidationTask(SafeTask):
    """
    Custom task class for source validation with entity failure handling.

    Inherits from SafeTask for automatic retry with exponential backoff.
    When a task fails (timeout, unhandled error), automatically updates
    BuildSource.validation_status to FAILED and publishes event.
    """

    def get_entity_failure_handler(
        self, kwargs: dict
    ) -> Optional[Callable[[str, str], None]]:
        """Update BuildSource status to FAILED when task fails."""
        source_id = kwargs.get("source_id")
        if not source_id:
            return None

        redis_client = self.redis

        def update_source_failed(status: str, error_message: str) -> None:
            try:
                db = get_database()
                source_repo = BuildSourceRepository(db)
                source_repo.update(
                    source_id,
                    validation_status=ValidationStatus.FAILED,
                    validation_error=error_message,
                    validation_completed_at=utc_now(),
                )
                # Publish event for frontend
                publish_source_update(
                    redis_client, source_id, "failed", error=error_message
                )
                cleanup_validation_stats(redis_client, source_id)
            except Exception as e:
                logger.warning(f"Failed to update source {source_id} status: {e}")

        return update_source_failed


def publish_source_update(
    redis_client: redis.Redis,
    source_id: str,
    status: str,
    progress: int = 0,
    stats: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
):
    """Publish source validation update to Redis for SSE broadcast."""
    import json

    try:
        payload = {
            "type": "SOURCE_UPDATE",
            "payload": {
                "source_id": source_id,
                "validation_status": status,
                "validation_progress": progress,
            },
        }
        if stats:
            payload["payload"]["validation_stats"] = stats
        if error:
            payload["payload"]["validation_error"] = error

        redis_client.publish("events", json.dumps(payload))
    except Exception as e:
        logger.error(f"Failed to publish source update: {e}")


# =============================================================================
# Task 1: Orchestrator
# =============================================================================


@celery_app.task(
    bind=True,
    base=SourceValidationTask,
    name="app.tasks.source_validation.validate_build_source_task",
    queue="dataset_validation",  # Share queue with dataset validation
    soft_time_limit=3600,
    time_limit=3660,
)
def validate_build_source_task(self, source_id: str) -> Dict[str, Any]:
    """
    Orchestrator task for distributed source validation.

    Reads CSV in chunks, groups by repo, and dispatches worker tasks.
    Uses Celery chord to aggregate results after all workers complete.

    Args:
        source_id: ID of the BuildSource to validate

    Returns:
        Dict with dispatch status
    """
    # Generate correlation_id for entire validation run
    correlation_id = str(uuid.uuid4())
    corr_prefix = f"[corr={correlation_id[:8]}]"

    # Set tracing context for structured logging
    TracingContext.set(
        correlation_id=correlation_id,
        source_id=source_id,
        pipeline_type="source_validation",
    )

    db = get_database()
    source_repo = BuildSourceRepository(db)

    try:
        logger.info(f"{corr_prefix}[source_validation] Starting for source {source_id}")

        # Load source
        source = source_repo.find_by_id(source_id)
        if not source:
            raise ValueError(f"BuildSource {source_id} not found")

        # Mark validation started
        source_repo.update(
            source_id,
            validation_status=ValidationStatus.VALIDATING,
            validation_started_at=utc_now(),
            validation_task_id=self.request.id,
            validation_progress=0,
            validation_error=None,
        )
        publish_source_update(self.redis, source_id, "validating", progress=0)

        # Get configuration
        file_path = source.file_path
        build_id_column = source.mapped_fields.build_id
        repo_name_column = source.mapped_fields.repo_name
        ci_provider_column = source.mapped_fields.ci_provider
        single_ci_provider = (
            (
                source.ci_provider.value
                if hasattr(source.ci_provider, "value")
                else source.ci_provider
            )
            if source.ci_provider
            else None
        )

        if not build_id_column or not repo_name_column:
            raise ValueError("Source column mapping not configured")

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
        source_build_repo = SourceBuildRepository(db)
        validated_builds = {
            b.build_id_from_source
            for b in source_build_repo.find_by_source(source_id, limit=100000)
            if b.build_id_from_source
        }

        if validated_builds:
            logger.info(
                f"Resuming: skipping {len(validated_builds)} already validated builds"
            )
            for repo_name in list(all_repo_builds.keys()):
                remaining = [
                    b
                    for b in all_repo_builds[repo_name]
                    if b["build_id"] not in validated_builds
                ]
                if remaining:
                    all_repo_builds[repo_name] = remaining
                else:
                    del all_repo_builds[repo_name]

        total_repos = len(all_repo_builds)
        total_builds = sum(len(builds) for builds in all_repo_builds.values())

        logger.info(f"Found {total_repos} repos, {total_builds} builds to validate")

        if total_repos == 0:
            source_repo.update(
                source_id,
                validation_status=ValidationStatus.COMPLETED,
                validation_completed_at=utc_now(),
                validation_progress=100,
                setup_step=2,
            )
            publish_source_update(self.redis, source_id, "completed", progress=100)
            return {"status": "completed", "message": "No valid repos found"}

        # Initialize Redis counters
        init_validation_stats(self.redis, source_id, total_repos, total_builds)

        # Chunk repos for parallel processing
        repo_chunks = list(
            chunk_dict(all_repo_builds, settings.VALIDATION_REPOS_PER_TASK)
        )

        # Update total chunks in Redis
        increment_validation_stat(
            self.redis, source_id, "total_chunks", len(repo_chunks)
        )

        repo_tasks = [
            validate_source_repo_chunk.si(
                source_id=source_id,
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
                    validate_source_builds_chunk.si(
                        source_id=source_id,
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
            aggregate_source_validation_results.si(
                source_id=source_id, correlation_id=correlation_id
            ),  # Final: Aggregate results
        ).apply_async()

        workflow_id = workflow.id if workflow else None
        logger.info(
            f"{corr_prefix}[source_validation] Dispatched {len(repo_chunks)} repo chunks, "
            f"workflow_id={workflow_id}"
        )

        return {
            "status": "dispatched",
            "total_repos": total_repos,
            "total_builds": total_builds,
            "chunks": len(repo_chunks),
            "workflow_id": str(workflow_id) if workflow_id else None,
            "correlation_id": correlation_id,
        }

    except Exception as e:
        logger.exception(f"{corr_prefix}[source_validation] Orchestrator failed: {e}")
        source_repo.update(
            source_id,
            validation_status=ValidationStatus.FAILED,
            validation_completed_at=utc_now(),
            validation_error=str(e),
        )
        publish_source_update(self.redis, source_id, "failed", error=str(e))
        raise


# =============================================================================
# Task 2: Repo Chunk Validator
# =============================================================================


@celery_app.task(
    bind=True,
    base=SourceValidationTask,
    name="app.tasks.source_validation.validate_source_repo_chunk",
    queue="dataset_validation",
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
)
def validate_source_repo_chunk(
    self,
    source_id: str,
    repo_builds_chunk: Dict[str, List[Dict[str, str]]],
    chunk_index: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Validate a chunk of repositories and dispatch build validation tasks.

    Args:
        source_id: Source being validated
        repo_builds_chunk: Dict mapping repo_name to build list
        chunk_index: Index of this chunk
        correlation_id: Correlation ID for tracing

    Returns:
        Dict with validation results for this chunk
    """
    db = get_database()
    raw_repo_repo = RawRepositoryRepository(db)
    source_repo_stats_repo = SourceRepoStatsRepository(db)

    repos_valid = 0
    repos_not_found = 0
    repos_private = 0
    valid_repos_data: List[Dict[str, Any]] = []

    with get_public_github_client() as client:
        for repo_name, builds in repo_builds_chunk.items():
            try:
                # Check repo exists using shared client
                repo_data = client.get_repository(repo_name)

                # Check if private
                if repo_data.get("private"):
                    repos_private += 1
                    increment_validation_stat(self.redis, source_id, "repos_private")
                    increment_validation_stat(
                        self.redis, source_id, "builds_not_found", len(builds)
                    )
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
                increment_validation_stat(self.redis, source_id, "repos_valid")

                # Extract CI provider from first build
                # All builds for same repo have same ci_provider
                ci_provider = builds[0].get("ci_provider") if builds else None

                source_repo_stats_repo.upsert_by_source_and_repo(
                    source_id=source_id,
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
                increment_validation_stat(self.redis, source_id, "repos_not_found")
                increment_validation_stat(
                    self.redis, source_id, "builds_not_found", len(builds)
                )

    # Update chunk completion
    increment_validation_stat(self.redis, source_id, "chunks_completed")

    # Publish progress update
    stats = get_validation_stats(self.redis, source_id)
    progress = calculate_progress(stats["chunks_completed"], stats["total_chunks"])
    publish_source_update(
        self.redis, source_id, "validating", progress=progress, stats=stats
    )

    return {
        "chunk_index": chunk_index,
        "repos_valid": repos_valid,
        "repos_not_found": repos_not_found,
        "repos_private": repos_private,
        "correlation_id": correlation_id,
    }


# =============================================================================
# Task 3: Build Chunk Validator
# =============================================================================


@celery_app.task(
    bind=True,
    base=SourceValidationTask,
    name="app.tasks.source_validation.validate_source_builds_chunk",
    queue="dataset_validation",
    soft_time_limit=300,
    time_limit=360,
    max_retries=3,
)
def validate_source_builds_chunk(
    self,
    source_id: str,
    repo_name: str,
    raw_repo_id: str,
    builds: List[Dict[str, str]],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Validate a chunk of builds for a single repository.

    Uses concurrent async requests for faster validation.

    Args:
        source_id: Source being validated
        repo_name: Repository full name
        raw_repo_id: RawRepository ObjectId string
        builds: List of build info dicts
        correlation_id: Correlation ID for tracing

    Returns:
        Dict with validation results
    """
    import asyncio

    from app.ci_providers.models import BuildConclusion, BuildStatus

    db = get_database()
    source_build_repo = SourceBuildRepository(db)
    raw_build_run_repo = RawBuildRunRepository(db)
    raw_repo_repo = RawRepositoryRepository(db)

    # Lookup raw_repo_id if not provided (dispatched from orchestrator)
    if raw_repo_id is None:
        raw_repo = raw_repo_repo.find_by_full_name(repo_name)
        if raw_repo:
            raw_repo_id = str(raw_repo.id)
        else:
            # Repo not validated yet or not found - skip builds
            logger.warning(
                f"RawRepository not found for {repo_name}, skipping build validation"
            )
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
    builds_to_insert: List[SourceBuild] = []

    # Determine CI provider from first build
    ci_provider_str = (
        builds[0].get("ci_provider", "github_actions") if builds else "github_actions"
    )
    ci_provider = CIProvider(ci_provider_str)

    # Get CI provider client with config from settings (includes token)
    ci_config = get_provider_config(ci_provider)
    ci_client = get_ci_provider(ci_provider, config=ci_config, db=db)

    # Hardcoded filters (matching model_ingestion.py behavior)
    exclude_bots = True
    only_completed = True

    build_ids = [b["build_id"] for b in builds]
    existing_builds = source_build_repo.find_many(
        {
            "source_id": ObjectId(source_id),
            "build_id_from_source": {"$in": build_ids},
        }
    )
    existing_map = {b.build_id_from_source: b for b in existing_builds}

    # Filter out already validated builds
    builds_to_validate = []
    for build_info in builds:
        build_id = build_info["build_id"]
        existing = existing_map.get(build_id)
        if existing:
            if existing.status == SourceBuildStatus.FOUND:
                builds_found += 1
            else:
                builds_not_found += 1
        else:
            builds_to_validate.append(build_info)

    # Fetch all build details concurrently
    async def fetch_build_details_batch() -> List[Any]:
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

    # Helper to check if build should be filtered (matching model_ingestion.py logic)
    def should_filter_build(build_data: BuildData) -> tuple[bool, str]:
        """Check if build should be filtered based on hardcoded filters."""
        # Check only_completed filter
        if only_completed and build_data.status != BuildStatus.COMPLETED:
            return True, "Build not completed"

        # Check exclude_bots filter
        if exclude_bots and getattr(build_data, "is_bot_commit", False):
            return True, "Bot commit"

        # Filter conclusions matching model_ingestion.py
        conclusion = build_data.conclusion
        if conclusion not in (
            BuildConclusion.SUCCESS,
            BuildConclusion.FAILURE,
        ):
            conclusion_str = (
                conclusion.value if hasattr(conclusion, "value") else conclusion
            )
            return True, f"Conclusion '{conclusion_str}' filtered"

        return False, ""

    # Process results
    for build_info, build_data in zip(builds_to_validate, build_results, strict=False):
        build_id = build_info["build_id"]

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
                    status=(
                        build_data.status.value
                        if hasattr(build_data.status, "value")
                        else build_data.status
                    ),
                    conclusion=(
                        build_data.conclusion.value
                        if hasattr(build_data.conclusion, "value")
                        else build_data.conclusion
                    ),
                    commit_sha=build_data.commit_sha,
                    commit_message=build_data.commit_message,
                    commit_author=build_data.commit_author,
                    branch=build_data.branch,
                    started_at=build_data.started_at,
                    completed_at=build_data.completed_at,
                    duration_seconds=build_data.duration_seconds,
                    web_url=build_data.web_url,
                    raw_data=build_data.raw_data,
                    is_bot_commit=build_data.is_bot_commit or False,
                )

                # Check if build should be filtered
                should_filter, filter_reason = should_filter_build(build_data)
                if should_filter:
                    builds_filtered += 1
                    builds_to_insert.append(
                        SourceBuild(
                            source_id=ObjectId(source_id),
                            build_id_from_source=build_id,
                            repo_name_from_source=repo_name,
                            raw_repo_id=ObjectId(raw_repo_id),
                            status=SourceBuildStatus.FILTERED,
                            raw_run_id=raw_build_run.id,
                            validation_error=f"Filtered: {filter_reason}",
                            validated_at=utc_now(),
                        )
                    )
                else:
                    # Build passed filters
                    builds_to_insert.append(
                        SourceBuild(
                            source_id=ObjectId(source_id),
                            build_id_from_source=build_id,
                            repo_name_from_source=repo_name,
                            raw_repo_id=ObjectId(raw_repo_id),
                            status=SourceBuildStatus.FOUND,
                            raw_run_id=raw_build_run.id,
                            validated_at=utc_now(),
                        )
                    )
                    builds_found += 1

            else:
                builds_to_insert.append(
                    SourceBuild(
                        source_id=ObjectId(source_id),
                        build_id_from_source=build_id,
                        repo_name_from_source=repo_name,
                        raw_repo_id=ObjectId(raw_repo_id) if raw_repo_id else None,
                        status=SourceBuildStatus.NOT_FOUND,
                        validation_error="Build not found or incomplete",
                        validated_at=utc_now(),
                    )
                )
                builds_not_found += 1

        except Exception as e:
            logger.warning(f"Error validating build {build_id}: {e}")
            builds_to_insert.append(
                SourceBuild(
                    source_id=ObjectId(source_id),
                    build_id_from_source=build_id,
                    repo_name_from_source=repo_name,
                    raw_repo_id=ObjectId(raw_repo_id) if raw_repo_id else None,
                    status=SourceBuildStatus.ERROR,
                    validation_error=str(e)[:500],
                    validated_at=utc_now(),
                )
            )
            builds_not_found += 1

    # Bulk insert builds
    if builds_to_insert:
        source_build_repo.bulk_create(builds_to_insert)

    # Update Redis counters
    increment_validation_stat(self.redis, source_id, "builds_found", builds_found)
    increment_validation_stat(
        self.redis, source_id, "builds_not_found", builds_not_found
    )
    increment_validation_stat(self.redis, source_id, "builds_filtered", builds_filtered)

    return {
        "repo_name": repo_name,
        "builds_found": builds_found,
        "builds_not_found": builds_not_found,
        "builds_filtered": builds_filtered,
        "correlation_id": correlation_id,
    }


# =============================================================================
# Task 4: Aggregator
# =============================================================================


@celery_app.task(
    bind=True,
    base=SourceValidationTask,
    name="app.tasks.source_validation.aggregate_source_validation_results",
    queue="dataset_validation",
    soft_time_limit=300,
    time_limit=360,
)
def aggregate_source_validation_results(
    self,
    source_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Aggregate validation results and finalize source.

    Called after all repo and build validation tasks complete.

    Args:
        source_id: Source being validated
        correlation_id: Correlation ID for tracing

    Returns:
        Dict with final validation stats
    """
    db = get_database()
    source_repo = BuildSourceRepository(db)
    source_build_repo = SourceBuildRepository(db)

    try:
        # Get final counts from database
        status_counts = source_build_repo.count_by_status(source_id)

        # Build final stats
        stats = ValidationStats(
            repos_total=status_counts.get("repos_total", 0),
            repos_valid=status_counts.get("repos_valid", 0),
            repos_invalid=status_counts.get("repos_invalid", 0),
            repos_not_found=status_counts.get("repos_not_found", 0),
            builds_total=sum(status_counts.values()),
            builds_found=status_counts.get(SourceBuildStatus.FOUND.value, 0),
            builds_not_found=status_counts.get(SourceBuildStatus.NOT_FOUND.value, 0)
            + status_counts.get(SourceBuildStatus.ERROR.value, 0),
            builds_filtered=status_counts.get(SourceBuildStatus.FILTERED.value, 0),
        )

        # Update source
        source_repo.update(
            source_id,
            validation_status=ValidationStatus.COMPLETED,
            validation_completed_at=utc_now(),
            validation_progress=100,
            validation_stats=stats,
            setup_step=2,
        )

        # Publish completion event
        publish_source_update(
            self.redis,
            source_id,
            "completed",
            progress=100,
            stats=stats.model_dump(),
        )

        # Cleanup Redis counters
        cleanup_validation_stats(self.redis, source_id)

        logger.info(
            f"[corr={correlation_id[:8]}] Source {source_id} validation completed: "
            f"{stats.builds_found} found, {stats.builds_not_found} not found"
        )

        return {
            "status": "completed",
            "stats": stats.model_dump(),
            "correlation_id": correlation_id,
        }

    except Exception as e:
        logger.exception(f"Failed to aggregate source validation: {e}")
        source_repo.update(
            source_id,
            validation_status=ValidationStatus.FAILED,
            validation_error=str(e),
            validation_completed_at=utc_now(),
        )
        publish_source_update(self.redis, source_id, "failed", error=str(e))
        raise
