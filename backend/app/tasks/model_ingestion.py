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
from app.ci_providers.models import BuildConclusion, BuildStatus
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.model_import_build import ModelImportBuild, ModelImportBuildStatus
from app.entities.model_repo_config import ModelImportStatus
from app.repositories.model_import_build import ModelImportBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask, SafeTask, TransientError
from app.tasks.model_processing import publish_status
from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
from app.tasks.shared import build_ingestion_workflow
from app.tasks.shared.events import publish_ingestion_build_update

logger = logging.getLogger(__name__)


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
    try:
        from app.entities.model_repo_config import ModelImportStatus
        from app.repositories.model_repo_config import ModelRepoConfigRepository

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

    # Update repo_config status
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "status": ModelImportStatus.FETCHING.value,
        },
    )

    publish_status(repo_config_id, "fetching", "Fetching builds from CI...")

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
    base=SafeTask,
    name="app.tasks.model_ingestion.fetch_builds_until_existing",
    queue="ingestion",
    soft_time_limit=600,
    time_limit=900,
    max_retries=3,
)
def fetch_builds_until_existing(
    self: SafeTask,
    repo_config_id: str,
    ci_provider: str,
    batch_size: int,
    only_with_logs: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Sequential fetch that stops when hitting existing builds.

    Uses 'since' parameter to only fetch builds NEWER than the newest existing build.
    This prevents fetching old builds that were not included in the initial sync.

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

    # Get newest existing build's created_at for "since" filter
    # This ensures we only fetch builds NEWER than what we already have
    newest_build = build_run_repo.get_latest_run(ObjectId(raw_repo_id))
    since_dt = newest_build.created_at if newest_build else None

    if since_dt:
        logger.info(f"{log_ctx} Fetching builds newer than {since_dt.isoformat()}")
    else:
        logger.info(f"{log_ctx} No existing builds, fetching all")

    page = 1
    total_new_builds = 0
    all_commit_shas = []
    all_ci_run_ids = []

    while True:
        logger.info(f"{log_ctx} Fetching page {page}")

        fetch_kwargs = {
            "since": since_dt,  # Only fetch builds newer than existing
            "limit": batch_size,
            "page": page,
            "exclude_bots": True,
            "only_with_logs": only_with_logs,
            "only_completed": True,
        }

        # Fetch page with error handling
        try:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                builds = loop.run_until_complete(
                    ci_instance.fetch_builds(full_name, **fetch_kwargs)
                )
            finally:
                loop.close()
                asyncio.set_event_loop(None)
        except Exception as e:
            # Raise TransientError for automatic retry with backoff
            raise TransientError(f"Failed to fetch builds from CI API: {e}") from e

        if not builds:
            logger.info(f"{log_ctx} Page {page}: No builds returned, stopping")
            break

        # Process builds and count new ones
        new_on_page = 0
        existing_on_page = 0

        for build in builds:
            if build.status != BuildStatus.COMPLETED:
                continue

            if build.conclusion in (
                BuildConclusion.SKIPPED,
                BuildConclusion.ACTION_REQUIRED,
                BuildConclusion.STALE,
            ):
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

            # Atomic upsert ModelImportBuild
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

        # Stop if we hit ANY existing build
        if existing_on_page > 0:
            logger.info(
                f"{log_ctx} Found {existing_on_page} existing builds on page {page}, stopping sync"
            )
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
        publish_status(repo_config_id, "processed", "No new builds found")
        repo_config_repo.update_repository(
            repo_config_id,
            {"status": ModelImportStatus.PROCESSED.value},
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
            "builds_missing_resource": 0,
        },
    )

    return {
        "status": "dispatched",
        "new_builds": total_new_builds,
        "pages": page,
    }


@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.model_ingestion.fetch_builds_batch",
    queue="ingestion",
    soft_time_limit=300,
    time_limit=360,
    max_retries=3,
)
def fetch_builds_batch(
    self: SafeTask,
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

    Uses SafeTask pattern:
    - TransientError: API failures → retry with backoff
    - Returns dict with page info and count of builds fetched
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

    # Fetch page - raise TransientError for API failures to trigger retry
    try:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            builds = loop.run_until_complete(ci_instance.fetch_builds(full_name, **fetch_kwargs))
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    except Exception as e:
        # Wrap as TransientError for automatic retry with backoff
        raise TransientError(f"Failed to fetch builds page {page}: {e}") from e

    if not builds:
        logger.info(f"{log_ctx} No builds found")
        return {"page": page, "builds": 0, "has_more": False}

    # Save builds and create ModelImportBuild records
    import_builds_to_insert = []

    for build in builds:
        if build.status != BuildStatus.COMPLETED:
            continue

        # Filter out builds that were skipped/cancelled/stale
        if build.conclusion in (
            BuildConclusion.SKIPPED,
            BuildConclusion.ACTION_REQUIRED,
            BuildConclusion.STALE,
        ):
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

    # If chord says 0 builds, mark as processed
    if total_from_results == 0:
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "status": ModelImportStatus.PROCESSED.value,
                "builds_fetched": 0,
            },
        )
        publish_status(repo_config_id, "processed", "No builds found")
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
        stats={
            "builds_fetched": total_fetched,
            "builds_ingested": 0,
        },
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

    # Get required resources based on template
    from app.services.dataset_template_service import DatasetTemplateService

    template_service = DatasetTemplateService(self.db)
    required_resources = template_service.get_required_resources_for_template("Risk Prediction")
    tasks_by_level = get_ingestion_tasks_by_level(list(required_resources))

    import_build_repo.init_resource_status(repo_config_id, list(required_resources))

    # Update DB and publish WebSocket for IN_PROGRESS status
    from app.entities.model_import_build import ResourceStatus

    total_builds = len(commit_shas)
    for resource in required_resources:
        # Persist IN_PROGRESS status to DB
        import_build_repo.update_resource_status_batch(
            repo_config_id,
            resource,
            ResourceStatus.IN_PROGRESS,
        )
        # Publish WebSocket event for real-time UI update
        publish_ingestion_build_update(
            repo_id=repo_config_id,
            resource=resource,
            status="in_progress",
            builds_affected=total_builds,
            pipeline_type="model",
        )

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
        pipeline_id=repo_config_id,
        pipeline_type="model",
    )

    # Callback only marks builds as INGESTED and sets final ingestion status
    callback = aggregate_model_ingestion_results.s(
        repo_config_id=repo_config_id,
        correlation_id=correlation_id,
    )

    if ingestion_workflow:
        logger.info(f"{log_ctx} Dispatching ingestion chord")
        # Use on_error on callback to handle chord failures gracefully
        error_callback = handle_ingestion_chord_error.s(
            repo_config_id=repo_config_id,
            correlation_id=correlation_id,
        )
        chord(ingestion_workflow, callback.on_error(error_callback)).apply_async()
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

    Parses results to update per-resource status, then marks builds as INGESTED.
    """

    from bson import ObjectId

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    now = datetime.utcnow()

    # === Determine per-build final status from resource_status in DB ===
    # FAILED: Any required resource has status = "failed" (actual error - RETRYABLE)
    # MISSING_RESOURCE: Logs expired (expected - NOT RETRYABLE)
    # INGESTED: All required resources completed

    # 1. Check if git_history failed (affects ALL builds)
    git_history_failed = import_build_repo.collection.count_documents(
        {
            "model_repo_config_id": ObjectId(repo_config_id),
            "status": ModelImportBuildStatus.INGESTING.value,
            "resource_status.git_history.status": "failed",
        }
    )

    if git_history_failed > 0:
        # Clone failed - mark all as FAILED
        import_build_repo.update_many_by_status(
            repo_config_id,
            from_status=ModelImportBuildStatus.INGESTING.value,
            updates={
                "status": ModelImportBuildStatus.FAILED.value,
                "ingestion_error": "Clone failed",
                "failed_at": now,
            },
        )
    else:
        # 2. Mark builds with failed git_worktree as FAILED
        import_build_repo.collection.update_many(
            {
                "model_repo_config_id": ObjectId(repo_config_id),
                "status": ModelImportBuildStatus.INGESTING.value,
                "resource_status.git_worktree.status": "failed",
            },
            {
                "$set": {
                    "status": ModelImportBuildStatus.FAILED.value,
                    "ingestion_error": "Worktree creation failed",
                    "failed_at": now,
                }
            },
        )

        # 3. Mark builds with failed build_logs as FAILED (retryable)
        # Note: We differentiate between actual failures and expired logs
        # For now, treat all log failures as MISSING_RESOURCE (not retryable)
        import_build_repo.collection.update_many(
            {
                "model_repo_config_id": ObjectId(repo_config_id),
                "status": ModelImportBuildStatus.INGESTING.value,
                "resource_status.build_logs.status": "failed",
            },
            {
                "$set": {
                    "status": ModelImportBuildStatus.MISSING_RESOURCE.value,
                    "ingestion_error": "Log download failed or expired",
                    "failed_at": now,
                }
            },
        )

        # 4. Mark remaining INGESTING builds as INGESTED
        import_build_repo.update_many_by_status(
            repo_config_id,
            from_status=ModelImportBuildStatus.INGESTING.value,
            updates={
                "status": ModelImportBuildStatus.INGESTED.value,
                "ingested_at": now,
            },
        )

    # Count by status to determine final state
    status_counts = import_build_repo.count_by_status(repo_config_id)
    ingested = status_counts.get(ModelImportBuildStatus.INGESTED.value, 0)
    missing_resource = status_counts.get(ModelImportBuildStatus.MISSING_RESOURCE.value, 0)
    failed = status_counts.get(ModelImportBuildStatus.FAILED.value, 0)

    # Determine final ingestion status - always INGESTED
    # User accepts current state (with or without failures) when starting processing
    final_status = ModelImportStatus.INGESTED
    if failed > 0 or missing_resource > 0:
        parts = [f"{ingested} ready"]
        if failed > 0:
            parts.append(f"{failed} failed (retryable)")
        if missing_resource > 0:
            parts.append(f"{missing_resource} missing resources")
        msg = f"Ingestion done: {', '.join(parts)}. Review or start processing."
    else:
        msg = f"Ingestion complete: {ingested} builds ready. Start processing when ready."

    # Update repo config with final status and timestamps
    total_builds = ingested + missing_resource + failed
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "status": final_status.value,
            "last_synced_at": now,
            "builds_fetched": total_builds,
            "builds_ingested": ingested,
            "builds_missing_resource": missing_resource,
            "builds_ingestion_failed": failed,
        },
    )

    logger.info(f"{corr_prefix}[aggregate_ingestion] {msg}")

    # Get resource status summary for stats
    resource_summary = import_build_repo.get_resource_status_summary(repo_config_id)

    publish_status(
        repo_config_id,
        final_status.value,
        msg,
        stats={
            "builds_fetched": total_builds,
            "builds_ingested": ingested,
            "builds_missing_resource": missing_resource,
            "builds_ingestion_failed": failed,
            "last_synced_at": now.isoformat(),
            "resource_status": resource_summary,
        },
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

    now = datetime.utcnow()

    # Mark all INGESTING builds as FAILED (chord failure = actual error, retryable)
    failed_count = import_build_repo.update_many_by_status(
        repo_config_id,
        from_status=ModelImportBuildStatus.INGESTING.value,
        updates={
            "status": ModelImportBuildStatus.FAILED.value,
            "ingestion_error": f"Ingestion chord failed: {error_msg}",
            "failed_at": now,
        },
    )

    logger.warning(f"{corr_prefix} Marked {failed_count} builds as FAILED (retryable)")

    # Check if any builds made it to INGESTED before failure
    ingested_builds = import_build_repo.find_by_repo_config(
        repo_config_id, status=ModelImportBuildStatus.INGESTED
    )

    if ingested_builds:
        # Some builds made it through - set INGESTED
        # User can decide to start processing or retry failed builds
        logger.info(
            f"{corr_prefix} {len(ingested_builds)} builds were INGESTED before failure. "
            f"Marked as INGESTED for user review."
        )
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "status": ModelImportStatus.INGESTED.value,
                "error_message": f"Ingestion partially failed: {error_msg}",
                "builds_ingestion_failed": failed_count,
            },
        )
        publish_status(
            repo_config_id,
            ModelImportStatus.INGESTED.value,
            f"Ingestion done: {len(ingested_builds)} ok, {failed_count} failed (retryable). "
            f"Review and retry or start processing.",
            stats={
                "builds_ingested": len(ingested_builds),
                "builds_ingestion_failed": failed_count,
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


# REINGEST FAILED BUILDS
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
    Retry FAILED import builds (actual errors only).

    Only retries builds with status=FAILED (actual errors like timeout, network failure).
    Does NOT retry MISSING_RESOURCE builds (expected - logs expired, commit not found).

    Also respects checkpoint: only retries builds with _id > last_processed_import_build_id.
    """
    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)

    # Get repo config for checkpoint
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    if not repo_config:
        logger.error(f"Repo config not found: {repo_config_id}")
        return {"status": "error", "message": "Repo config not found"}

    # Find FAILED builds after checkpoint (not MISSING_RESOURCE - those are not retryable)
    checkpoint_id = repo_config.last_processed_import_build_id
    failed_builds = import_build_repo.find_failed_builds(repo_config_id, after_id=checkpoint_id)

    if not failed_builds:
        # Also count missing_resource for user feedback
        missing_count = import_build_repo.count_missing_resource_after_checkpoint(
            repo_config_id, checkpoint_id
        )
        msg = "No failed builds to retry"
        if missing_count > 0:
            msg += f" ({missing_count} builds have missing resources - not retryable)"
        logger.info(f"{msg} for {repo_config_id}")
        return {
            "status": "no_failed_builds",
            "failed_count": 0,
            "missing_resource_count": missing_count,
            "checkpoint": str(checkpoint_id) if checkpoint_id else None,
        }

    correlation_id = str(uuid.uuid4())[:8]
    logger.info(
        f"[corr={correlation_id}] Found {len(failed_builds)} failed builds "
        f"after checkpoint {checkpoint_id} for {repo_config_id}"
    )

    # Collect commit SHAs and CI run IDs from failed builds
    commit_shas = []
    ci_run_ids = []

    # Reset status to FETCHED for retry, clear error fields
    reset_count = 0
    for import_build in failed_builds:
        try:
            import_build_repo.update_one(
                str(import_build.id),
                {
                    "status": ModelImportBuildStatus.FETCHED.value,
                    "ingestion_error": None,
                    "failed_at": None,
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
        "total_failed": len(failed_builds),
        "correlation_id": correlation_id,
    }
