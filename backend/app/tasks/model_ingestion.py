"""
Model Ingestion Tasks - Resource preparation for model training builds.

This module uses chord-based task pattern with database-driven state:
1. ingest_model_builds - Orchestrator: Dispatch fetch batch tasks
2. fetch_builds_batch - Fetches one page, creates ModelImportBuild records
3. aggregate_fetch_results - Chord callback: Query DB for pending builds
4. dispatch_ingestion - Build ingestion workflow from DB records
5. aggregate_model_ingestion_results - Mark builds as READY

Flow (chord pattern with DB state):
  ingest_model_builds
      └── chord(
              group(fetch_builds_batch tasks),
              aggregate_fetch_results
          )
          └── dispatch_ingestion
              └── chord(
                      ingestion_workflow,
                      aggregate_model_ingestion_results
                  )
                  └── dispatch_build_processing
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.ci_providers import CIProvider, get_ci_provider, get_provider_config
from app.ci_providers.models import BuildStatus
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.model_import_build import ModelImportBuild, ModelImportBuildStatus
from app.entities.model_repo_config import ModelImportStatus
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.repositories.model_import_build import ModelImportBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.model_processing import dispatch_build_processing, publish_status
from app.tasks.pipeline.feature_dag._metadata import get_required_resources_for_features
from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
from app.tasks.pipeline.shared.resources import FeatureResource
from app.tasks.shared import build_ingestion_workflow

logger = logging.getLogger(__name__)


def get_required_resources_for_template(db, template_name: str = "TravisTorrent Full") -> set:
    """Get required resources based on dataset template."""
    template_repo = DatasetTemplateRepository(db)
    template = template_repo.find_by_name(template_name)
    if template and template.feature_names:
        feature_set = set(template.feature_names)
        return get_required_resources_for_features(feature_set)
    return {r.value for r in FeatureResource}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.ingest_model_builds",
    queue="ingestion",
    soft_time_limit=120,
    time_limit=180,
)
def ingest_model_builds(
    self: PipelineTask,
    repo_config_id: str,
    ci_provider: str,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
    batch_size: Optional[int] = None,
    sync_until_existing: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Orchestrator: Dispatch fetch batch tasks as chord.

    Args:
        repo_config_id: The model repo config ID
        ci_provider: CI provider to use (e.g., "github_actions")
        max_builds: Maximum number of builds to fetch (ignored if sync_until_existing=True)
        since_days: Only fetch builds from the last N days (ignored if sync_until_existing=True)
        only_with_logs: Only fetch builds with logs available
        batch_size: Number of builds per page
        sync_until_existing: If True, fetch sequentially until hitting existing builds
        correlation_id: Optional correlation ID for tracing (generates new if not provided)

    Flow:
        ingest_model_builds
            └── chord(
                    group(fetch_builds_batch tasks per page),
                    aggregate_fetch_results
                )
    """
    # Use provided correlation_id or generate new one
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    corr_prefix = f"[corr={correlation_id[:8]}]"

    batch_size = batch_size or settings.INGESTION_BUILDS_PER_PAGE

    # Set tracing context
    TracingContext.set(
        correlation_id=correlation_id,
        repo_id=repo_config_id,
        pipeline_type="model_ingestion",
    )

    repo_config_repo = ModelRepoConfigRepository(self.db)

    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        raise ValueError(f"ModelRepoConfig {repo_config_id} not found")

    logger.info(f"{corr_prefix}[model_ingestion] Starting for {repo_config.full_name}")

    publish_status(repo_config_id, "ingesting", "Starting fetch...")

    # Route to appropriate fetch strategy
    if sync_until_existing:
        # Sequential fetch that stops when hitting existing builds
        logger.info(f"{corr_prefix} Using sync_until_existing mode")
        fetch_builds_until_existing.delay(
            repo_config_id=repo_config_id,
            ci_provider=ci_provider,
            batch_size=batch_size,
            only_with_logs=only_with_logs,
            correlation_id=correlation_id,
        )
        return {
            "status": "dispatched",
            "repo_config_id": repo_config_id,
            "correlation_id": correlation_id,
            "mode": "sync_until_existing",
        }

    # Original parallel fetch mode
    estimated_pages = (max_builds // batch_size + 1) if max_builds else 10

    # Build fetch tasks for each page
    fetch_tasks = []
    remaining = max_builds
    for page in range(1, estimated_pages + 1):
        api_limit = min(batch_size, remaining) if remaining else batch_size
        fetch_tasks.append(
            fetch_builds_batch.si(
                repo_config_id=repo_config_id,
                ci_provider=ci_provider,
                page=page,
                batch_size=api_limit,
                since_days=since_days,
                only_with_logs=only_with_logs,
                correlation_id=correlation_id,
            )
        )
        if remaining:
            remaining = max(0, remaining - api_limit)
            if remaining == 0:
                break

    # Dispatch chord: fetch all pages → aggregate results
    workflow = chord(
        group(fetch_tasks),
        aggregate_fetch_results.s(
            repo_config_id=repo_config_id,
            correlation_id=correlation_id,
        ),
    )
    workflow.apply_async()

    logger.info(f"{corr_prefix} Dispatched {len(fetch_tasks)} fetch tasks")

    return {
        "status": "dispatched",
        "repo_config_id": repo_config_id,
        "correlation_id": correlation_id,
        "fetch_tasks": len(fetch_tasks),
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.fetch_builds_until_existing",
    queue="ingestion",
    soft_time_limit=600,
    time_limit=900,
)
def fetch_builds_until_existing(
    self: PipelineTask,
    repo_config_id: str,
    ci_provider: str,
    batch_size: int,
    only_with_logs: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Sequential fetch that stops when hitting existing builds.

    Fetches pages one by one from newest to oldest. Stops when
    all builds on a page already exist in the database (COMPLETED or PARTIAL).

    After fetching, dispatches ingestion for new builds.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[sync_until_existing]"

    repo_config_repo = ModelRepoConfigRepository(self.db)
    build_run_repo = RawBuildRunRepository(self.db)
    import_build_repo = ModelImportBuildRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        return {"status": "error", "error": "Config not found"}

    raw_repo_id = str(repo_config.raw_repo_id)
    full_name = repo_config.full_name

    # Get CI provider instance
    ci_provider_enum = CIProvider(ci_provider)
    provider_config = get_provider_config(ci_provider_enum)
    ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

    # Get RawRepository for later
    raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
    if not raw_repo:
        return {"status": "error", "error": "RawRepository not found"}

    page = 1
    total_new_builds = 0
    all_commit_shas = []
    all_ci_run_ids = []

    while True:
        logger.info(f"{log_ctx} Fetching page {page}")

        fetch_kwargs = {
            "limit": batch_size,
            "page": page,
            "exclude_bots": True,
            "only_with_logs": only_with_logs,
            "only_completed": True,
        }

        # Fetch page
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            builds = loop.run_until_complete(ci_instance.fetch_builds(full_name, **fetch_kwargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        if not builds:
            logger.info(f"{log_ctx} Page {page}: No builds returned, stopping")
            break

        # Process builds and count new ones
        new_on_page = 0
        existing_on_page = 0

        for build in builds:
            if build.status != BuildStatus.COMPLETED:
                continue

            if not build.build_id:
                continue

            # Check if RawBuildRun already exists - if so, skip it (already imported)
            existing_run = build_run_repo.find_by_build_id(ObjectId(raw_repo_id), build.build_id)

            if existing_run:
                # Build already exists in database, count as existing and skip
                existing_on_page += 1
                continue

            # New build - save to RawBuildRun
            raw_build_run = build_run_repo.upsert_by_business_key(
                raw_repo_id=ObjectId(raw_repo_id),
                build_id=build.build_id,
                provider=ci_provider_enum.value,
                build_number=build.build_number,
                repo_name=full_name,
                branch=build.branch or "",
                commit_sha=build.commit_sha,
                commit_message=build.commit_message,
                commit_author=build.commit_author,
                status=build.status,
                conclusion=build.conclusion,
                created_at=build.created_at or datetime.now(timezone.utc),
                started_at=None,
                completed_at=build.created_at or datetime.now(timezone.utc),
                duration_seconds=build.duration_seconds,
                web_url=build.web_url,
                logs_url=None,
                logs_available=build.logs_available or False,
                logs_path=None,
                raw_data=build.raw_data or {},
                is_bot_commit=build.is_bot_commit or False,
            )

            # Atomic upsert ModelImportBuild (idempotent)
            import_build_repo.upsert_by_business_key(
                config_id=repo_config_id,
                raw_build_run_id=str(raw_build_run.id),
                status=ModelImportBuildStatus.FETCHED,
                ci_run_id=raw_build_run.ci_run_id,
                commit_sha=build.commit_sha or "",
            )

            new_on_page += 1
            all_commit_shas.append(build.commit_sha)
            all_ci_run_ids.append(build.build_id)

        total_new_builds += new_on_page
        logger.info(f"{log_ctx} Page {page}: {new_on_page} new, {existing_on_page} existing")

        # Stop if all builds on this page already exist
        if new_on_page == 0 and len(builds) > 0:
            logger.info(f"{log_ctx} All builds on page {page} already exist, stopping sync")
            break

        # Stop if no more pages
        if len(builds) < batch_size:
            logger.info(f"{log_ctx} No more pages (got {len(builds)} < {batch_size})")
            break

        page += 1

    logger.info(f"{log_ctx} Sync complete: {total_new_builds} new builds found")

    # Update repo config - INCREMENT builds_fetched
    repo_config_repo.increment_builds_fetched(
        ObjectId(repo_config_id),
        total_new_builds,
    )

    if total_new_builds == 0:
        publish_status(repo_config_id, "imported", "No new builds found")
        repo_config_repo.update_repository(
            repo_config_id,
            {"status": ModelImportStatus.IMPORTED.value},
        )
        return {"status": "completed", "new_builds": 0, "pages": page}

    # Dispatch ingestion for new builds
    dispatch_ingestion.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=raw_repo_id,
        github_repo_id=raw_repo.github_repo_id,
        full_name=full_name,
        ci_provider=ci_provider,
        commit_shas=list(set(all_commit_shas)),
        ci_run_ids=list(set(all_ci_run_ids)),
        correlation_id=correlation_id,
    )

    publish_status(
        repo_config_id,
        "ingesting",
        f"Preparing resources for {total_new_builds} new builds...",
        stats={
            "builds_fetched": total_new_builds,
            "builds_processed": 0,
            "builds_failed": 0,
        },
    )

    return {
        "status": "dispatched",
        "new_builds": total_new_builds,
        "pages": page,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.fetch_builds_batch",
    queue="ingestion",
    soft_time_limit=300,
    time_limit=360,
)
def fetch_builds_batch(
    self: PipelineTask,
    repo_config_id: str,
    ci_provider: str,
    page: int,
    batch_size: int,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Fetch a single page of builds and create ModelImportBuild records.

    Returns:
        Dict with page info and count of builds fetched
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[fetch_batch][page={page}]"

    repo_config_repo = ModelRepoConfigRepository(self.db)
    build_run_repo = RawBuildRunRepository(self.db)
    import_build_repo = ModelImportBuildRepository(self.db)

    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        return {"page": page, "builds": 0, "error": "Config not found"}

    raw_repo_id = str(repo_config.raw_repo_id)
    full_name = repo_config.full_name

    since_dt = datetime.now(timezone.utc) - timedelta(days=since_days) if since_days else None

    # Get CI provider instance
    ci_provider_enum = CIProvider(ci_provider)
    provider_config = get_provider_config(ci_provider_enum)
    ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

    fetch_kwargs = {
        "since": since_dt,
        "limit": batch_size,
        "page": page,
        "exclude_bots": True,
        "only_with_logs": only_with_logs,
        "only_completed": True,
    }

    # Fetch page
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        builds = loop.run_until_complete(ci_instance.fetch_builds(full_name, **fetch_kwargs))
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    if not builds:
        logger.info(f"{log_ctx} No builds found")
        return {"page": page, "builds": 0, "has_more": False}

    # Save builds and create ModelImportBuild records
    import_builds_to_insert = []

    for build in builds:
        if build.status != BuildStatus.COMPLETED:
            continue

        if not build.build_id:
            logger.warning(
                f"{log_ctx} Skipping build with null build_id: "
                f"build_number={build.build_number}, "
                f"status={build.status}, "
                f"commit_sha={build.commit_sha}, "
                f"web_url={build.web_url}, "
                f"raw_data_keys={list(build.raw_data.keys()) if build.raw_data else []}"
            )
            continue

        # Save to RawBuildRun
        raw_build_run = build_run_repo.upsert_by_business_key(
            raw_repo_id=ObjectId(raw_repo_id),
            build_id=build.build_id,
            provider=ci_provider_enum.value,
            build_number=build.build_number,
            repo_name=full_name,
            branch=build.branch or "",
            commit_sha=build.commit_sha,
            commit_message=build.commit_message,
            commit_author=build.commit_author,
            status=build.status,
            conclusion=build.conclusion,
            created_at=build.created_at or datetime.now(timezone.utc),
            started_at=None,
            completed_at=build.created_at or datetime.now(timezone.utc),
            duration_seconds=build.duration_seconds,
            web_url=build.web_url,
            logs_url=None,
            logs_available=build.logs_available or False,
            logs_path=None,
            raw_data=build.raw_data or {},
            is_bot_commit=build.is_bot_commit or False,
        )

        # Check if ModelImportBuild already exists
        existing = import_build_repo.find_by_business_key(repo_config_id, str(raw_build_run.id))
        if existing:
            continue  # Already created

        # Create ModelImportBuild
        import_build = ModelImportBuild(
            model_repo_config_id=ObjectId(repo_config_id),
            raw_build_run_id=raw_build_run.id,
            status=ModelImportBuildStatus.FETCHED,
            ci_run_id=raw_build_run.ci_run_id,
            commit_sha=build.commit_sha or "",
        )
        import_builds_to_insert.append(import_build)

    # Bulk insert
    if import_builds_to_insert:
        import_build_repo.bulk_insert(import_builds_to_insert)

    has_more = len(builds) >= batch_size
    logger.info(f"{log_ctx} Saved {len(import_builds_to_insert)} builds, has_more={has_more}")

    return {
        "page": page,
        "builds": len(import_builds_to_insert),
        "has_more": has_more,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.aggregate_fetch_results",
    queue="ingestion",
    soft_time_limit=60,
    time_limit=120,
)
def aggregate_fetch_results(
    self: PipelineTask,
    results: List[Dict[str, Any]],
    repo_config_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Aggregate fetch results and dispatch ingestion.

    Uses chord results (guaranteed complete) to count fetched builds,
    then queries DB for actual records.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[aggregate_fetch]"

    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    # Sum up builds from chord results (these are guaranteed complete)
    total_from_results = sum(r.get("builds", 0) for r in results if r)
    logger.info(f"{log_ctx} Chord results: {total_from_results} builds from {len(results)} tasks")

    # If chord says 0 builds, mark as imported
    if total_from_results == 0:
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "status": ModelImportStatus.IMPORTED.value,
                "builds_fetched": 0,
            },
        )
        publish_status(repo_config_id, "imported", "No builds found")
        return {"status": "completed", "builds": 0}

    # Query DB for actual records (should match chord results)
    fetched_builds = import_build_repo.find_fetched_builds(repo_config_id)
    total_fetched = len(fetched_builds)

    # Log discrepancy if any (shouldn't happen with chord)
    if total_fetched != total_from_results:
        logger.warning(f"{log_ctx} Discrepancy: chord={total_from_results}, db={total_fetched}")

    logger.info(f"{log_ctx} Found {total_fetched} fetched builds in DB")

    # Update repo config
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    repo_config_repo.update_repository(
        repo_config_id,
        {"builds_fetched": total_fetched},
    )

    # Get commit SHAs and CI run IDs from fetched builds
    commit_shas = import_build_repo.get_commit_shas(repo_config_id)
    ci_run_ids = import_build_repo.get_ci_run_ids(repo_config_id)

    # Get RawRepository
    raw_repo = raw_repo_repo.find_by_id(repo_config.raw_repo_id)
    if not raw_repo:
        raise ValueError(f"RawRepository {repo_config.raw_repo_id} not found")

    # Dispatch ingestion
    dispatch_ingestion.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        github_repo_id=raw_repo.github_repo_id,
        full_name=repo_config.full_name,
        ci_provider=repo_config.ci_provider,
        commit_shas=commit_shas,
        ci_run_ids=ci_run_ids,
        correlation_id=correlation_id,
    )

    publish_status(
        repo_config_id,
        "ingesting",
        f"Preparing resources for {total_fetched} builds...",
    )

    return {
        "status": "dispatched",
        "builds": total_fetched,
        "commits": len(commit_shas),
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.dispatch_ingestion",
    queue="ingestion",
    soft_time_limit=120,
    time_limit=180,
)
def dispatch_ingestion(
    self: PipelineTask,
    repo_config_id: str,
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    ci_provider: str,
    commit_shas: List[str],
    ci_run_ids: List[str],
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Build and dispatch ingestion workflow.

    After ingestion completes, dispatches processing.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[dispatch_ingestion]"

    # Mark all FETCHED builds as INGESTING
    import_build_repo = ModelImportBuildRepository(self.db)
    import_build_repo.update_many_by_status(
        repo_config_id,
        from_status=ModelImportBuildStatus.FETCHED.value,
        updates={
            "status": ModelImportBuildStatus.INGESTING.value,
            "ingestion_started_at": datetime.utcnow(),
        },
    )

    # Get required resources
    required_resources = get_required_resources_for_template(self.db)
    tasks_by_level = get_ingestion_tasks_by_level(list(required_resources))

    logger.info(f"{log_ctx} Resources={sorted(required_resources)}, tasks={tasks_by_level}")

    # Build ingestion workflow
    ingestion_workflow = build_ingestion_workflow(
        tasks_by_level=tasks_by_level,
        raw_repo_id=raw_repo_id,
        github_repo_id=github_repo_id,
        full_name=full_name,
        build_ids=ci_run_ids,
        commit_shas=commit_shas,
        ci_provider=ci_provider,
        correlation_id=correlation_id,
    )

    # Callback only marks builds as INGESTED and sets final ingestion status
    # (NO auto-dispatch to processing - user triggers Phase 2 manually)
    callback = aggregate_model_ingestion_results.s(
        repo_config_id=repo_config_id,
        correlation_id=correlation_id,
    )

    if ingestion_workflow:
        logger.info(f"{log_ctx} Dispatching ingestion chord")
        # Use link_error to handle chord failures gracefully
        error_callback = handle_ingestion_chord_error.s(
            repo_config_id=repo_config_id,
            correlation_id=correlation_id,
        )
        chord(ingestion_workflow, callback).apply_async(link_error=error_callback)
    else:
        logger.info(f"{log_ctx} No ingestion needed, marking as complete")
        # No ingestion tasks needed - directly mark as complete
        aggregate_model_ingestion_results.delay(
            results=[],
            repo_config_id=repo_config_id,
            correlation_id=correlation_id,
        )

    return {"status": "dispatched", "resources": list(required_resources)}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.aggregate_model_ingestion_results",
    queue="ingestion",
    soft_time_limit=30,
    time_limit=60,
)
def aggregate_model_ingestion_results(
    self: PipelineTask,
    results: Any,
    repo_config_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Chord callback after ingestion workflow completes.

    Marks builds as INGESTED and sets final ingestion status.
    Does NOT auto-dispatch processing - user triggers Phase 2 manually.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Mark all INGESTING builds as INGESTED
    updated_count = import_build_repo.update_many_by_status(
        repo_config_id,
        from_status=ModelImportBuildStatus.INGESTING.value,
        updates={
            "status": ModelImportBuildStatus.INGESTED.value,
            "ingested_at": datetime.utcnow(),
        },
    )

    # Count by status to determine final state
    status_counts = import_build_repo.count_by_status(repo_config_id)
    ingested = status_counts.get(ModelImportBuildStatus.INGESTED.value, 0)
    failed = status_counts.get(ModelImportBuildStatus.FAILED.value, 0)

    logger.debug(f"{corr_prefix} Updated {updated_count} builds to INGESTED")

    # Determine final ingestion status
    if failed > 0:
        final_status = ModelImportStatus.INGESTION_PARTIAL
        msg = f"Ingestion partial: {ingested} ok, {failed} failed. Review or start processing."
    else:
        final_status = ModelImportStatus.INGESTION_COMPLETE
        msg = f"Ingestion complete: {ingested} builds ready. Start processing when ready."

    repo_config_repo.update_repository(
        repo_config_id,
        {"status": final_status.value},
    )

    logger.info(f"{corr_prefix}[aggregate_ingestion] {msg}")

    publish_status(
        repo_config_id,
        final_status.value,
        msg,
        stats={
            "builds_ingested": ingested,
            "builds_failed": failed,
        },
    )

    return {
        "status": "completed",
        "final_status": final_status.value,
        "builds_ingested": ingested,
        "builds_failed": failed,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.handle_ingestion_chord_error",
    queue="ingestion",
    soft_time_limit=60,
    time_limit=120,
)
def handle_ingestion_chord_error(
    self: PipelineTask,
    request,
    exc,
    traceback,
    repo_config_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Error callback for ingestion chord failure.

    Principle: Never fail the whole pipeline for a single build failure.

    When ingestion chord fails (clone_repo, create_worktrees, etc.):
    1. Mark all INGESTING builds as FAILED with ingestion_error
    2. Update repo config status to PARTIAL (not FAILED)
    3. Still dispatch processing for any builds that made it through

    Args:
        request: Celery request object
        exc: Exception that caused the failure
        traceback: Traceback string
        repo_config_id: The model repo config ID
        correlation_id: Correlation ID for tracing
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    error_msg = str(exc) if exc else "Unknown ingestion error"

    logger.error(f"{corr_prefix} Ingestion chord failed for {repo_config_id}: {error_msg}")

    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Mark all INGESTING builds as FAILED
    failed_count = import_build_repo.update_many_by_status(
        repo_config_id,
        from_status=ModelImportBuildStatus.INGESTING.value,
        updates={
            "status": ModelImportBuildStatus.FAILED.value,
            "ingestion_error": f"Ingestion chord failed: {error_msg}",
        },
    )

    logger.warning(f"{corr_prefix} Marked {failed_count} builds as FAILED")

    # Check if any builds made it to INGESTED before failure
    ingested_builds = import_build_repo.find_by_repo_config(
        repo_config_id, status=ModelImportBuildStatus.INGESTED
    )

    if ingested_builds:
        # Some builds made it through - set INGESTION_PARTIAL
        # User can decide to start processing or retry failed builds
        logger.info(
            f"{corr_prefix} {len(ingested_builds)} builds were INGESTED before failure. "
            f"Marked as INGESTION_PARTIAL for user review."
        )
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "status": ModelImportStatus.INGESTION_PARTIAL.value,
                "error_message": f"Ingestion partially failed: {error_msg}",
            },
        )
        publish_status(
            repo_config_id,
            ModelImportStatus.INGESTION_PARTIAL.value,
            f"Ingestion partial: {len(ingested_builds)} ok, {failed_count} failed. "
            f"Review and retry or start processing.",
            stats={
                "builds_ingested": len(ingested_builds),
                "builds_failed": failed_count,
            },
        )
    else:
        # No builds made it - mark as failed but allow retry
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
            f"Ingestion failed: {error_msg}. Use Retry Failed Ingestion to retry.",
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
    name="app.tasks.model_ingestion.start_processing_phase",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def start_processing_phase(
    self: PipelineTask,
    repo_config_id: str,
) -> Dict[str, Any]:
    """
    Phase 2: Start processing phase (manually triggered by user).

    Validates that ingestion is complete before starting feature extraction.
    Only proceeds if status is INGESTION_COMPLETE or INGESTION_PARTIAL.
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

    valid_statuses = [
        ModelImportStatus.INGESTION_COMPLETE.value,
        ModelImportStatus.INGESTION_PARTIAL.value,
    ]
    if repo_config.status not in valid_statuses:
        msg = (
            f"Cannot start processing: status is {repo_config.status}. "
            f"Expected: {valid_statuses}"
        )
        logger.warning(f"{log_ctx} {msg}")
        return {"status": "error", "message": msg}

    # Query INGESTED builds (sorted by creation time - oldest first for history features)
    ingested_builds = import_build_repo.find_by_repo_config(
        repo_config_id, status=ModelImportBuildStatus.INGESTED
    )

    if not ingested_builds:
        logger.info(f"{log_ctx} No ingested builds for {repo_config_id}")
        return {"status": "completed", "builds": 0, "message": "No builds to process"}

    # Extract raw_build_run_ids
    raw_build_run_ids = [str(b.raw_build_run_id) for b in ingested_builds]

    # Update status to PROCESSING
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.PROCESSING.value},
    )

    # Dispatch processing with correlation_id
    dispatch_build_processing.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        raw_build_run_ids=raw_build_run_ids,
        correlation_id=correlation_id,
    )

    logger.info(f"{log_ctx} Dispatched processing for {len(raw_build_run_ids)} builds")

    publish_status(
        repo_config_id,
        "processing",
        f"Processing {len(raw_build_run_ids)} builds...",
    )

    return {"status": "dispatched", "builds": len(raw_build_run_ids)}


# =============================================================================
# REINGEST FAILED BUILDS
# =============================================================================


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.ingestion.reingest_failed_builds",
    queue="ingestion",
    soft_time_limit=600,
    time_limit=900,
)
def reingest_failed_builds(
    self: PipelineTask,
    repo_config_id: str,
) -> Dict[str, Any]:
    """
    Retry only FAILED import builds.

    This task finds all ModelImportBuild with status=FAILED,
    resets them to FETCHED, and re-triggers the ingestion pipeline.
    """
    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Find failed imports
    failed_imports = import_build_repo.find_failed_imports(repo_config_id)

    if not failed_imports:
        logger.info(f"No failed imports found for {repo_config_id}")
        return {"status": "no_failed_imports", "count": 0}

    correlation_id = str(uuid.uuid4())[:8]
    logger.info(
        f"[corr={correlation_id}] Found {len(failed_imports)} failed imports for {repo_config_id}"
    )

    # Get repo config for metadata
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repo config not found: {repo_config_id}")
        return {"status": "error", "message": "Repo config not found"}

    # Collect commit SHAs and CI run IDs from failed imports
    commit_shas = []
    ci_run_ids = []

    # Reset status to FETCHED for retry
    reset_count = 0
    for import_build in failed_imports:
        try:
            import_build_repo.update_one(
                str(import_build.id),
                {
                    "status": ModelImportBuildStatus.FETCHED.value,
                    "ingestion_error": None,
                },
            )
            reset_count += 1

            # Collect data for dispatch_ingestion
            if import_build.commit_sha:
                commit_shas.append(import_build.commit_sha)
            ci_run_ids.append(import_build.ci_run_id)

        except Exception as e:
            logger.warning(f"Failed to reset import build {import_build.id}: {e}")

    if not ci_run_ids:
        logger.warning(f"No CI run IDs to reingest for {repo_config_id}")
        return {"status": "no_runs_to_reingest", "count": 0}

    # Update repo status
    repo_config_repo.update_repository(
        repo_config_id,
        {"status": ModelImportStatus.INGESTING.value},
    )

    # Get raw repo info
    raw_repo = RawRepositoryRepository(self.db).find_by_id(str(repo_config.raw_repo_id))
    if not raw_repo:
        logger.error(f"Raw repo not found: {repo_config.raw_repo_id}")
        return {"status": "error", "message": "Raw repo not found"}

    # Trigger ingestion with all required parameters
    dispatch_ingestion.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        github_repo_id=raw_repo.github_repo_id,
        full_name=raw_repo.full_name,
        ci_provider=repo_config.ci_provider or CIProvider.GITHUB_ACTIONS.value,
        commit_shas=commit_shas,
        ci_run_ids=ci_run_ids,
        correlation_id=correlation_id,
    )

    publish_status(
        repo_config_id,
        "ingesting",
        f"Retrying {reset_count} failed imports...",
    )

    return {
        "status": "queued",
        "imports_reset": reset_count,
        "total_failed": len(failed_imports),
        "correlation_id": correlation_id,
    }
