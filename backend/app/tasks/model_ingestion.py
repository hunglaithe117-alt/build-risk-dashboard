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
from celery import chain as celery_chain
from celery import chord, group

from app.celery_app import celery_app
from app.ci_providers import CIProvider, get_ci_provider, get_provider_config
from app.ci_providers.models import BuildStatus
from app.config import settings
from app.core.tracing import TracingContext
from app.entities.enums import ModelImportStatus
from app.entities.model_import_build import ModelImportBuild, ModelImportBuildStatus
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.repositories.model_import_build import ModelImportBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.github.exceptions import GithubRateLimitError, GithubRetryableError
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
) -> Dict[str, Any]:
    """
    Orchestrator: Dispatch fetch batch tasks as chord.

    Flow:
        ingest_model_builds
            └── chord(
                    group(fetch_builds_batch tasks per page),
                    aggregate_fetch_results
                )
    """
    # Generate correlation_id for tracing entire flow
    correlation_id = str(uuid.uuid4())
    corr_prefix = f"[corr={correlation_id[:8]}]"

    batch_size = batch_size or settings.MODEL_FETCH_BATCH_SIZE

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

    # Increment import version
    new_version = (repo_config.import_version or 0) + 1
    repo_config_repo.update_repository(
        repo_config_id,
        {
            "import_version": new_version,
            "import_status": ModelImportStatus.IMPORTING.value,
            "import_started_at": datetime.utcnow(),
        },
    )
    publish_status(repo_config_id, "importing", "Starting fetch...")

    # Estimate pages needed (we'll dispatch tasks for pages 1..N)
    # For simplicity, dispatch first page and let it chain more if needed
    # OR dispatch multiple pages in parallel if we know max_builds
    estimated_pages = (max_builds // batch_size + 1) if max_builds else 10  # Default 10 pages

    # Build fetch tasks for each page
    fetch_tasks = [
        fetch_builds_batch.s(
            repo_config_id=repo_config_id,
            ci_provider=ci_provider,
            page=page,
            batch_size=batch_size,
            since_days=since_days,
            only_with_logs=only_with_logs,
            import_version=new_version,
            correlation_id=correlation_id,
        )
        for page in range(1, estimated_pages + 1)
    ]

    # Dispatch chord: fetch all pages → aggregate results
    workflow = chord(
        group(fetch_tasks),
        aggregate_fetch_results.s(
            repo_config_id=repo_config_id,
            import_version=new_version,
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
        "import_version": new_version,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.fetch_builds_batch",
    queue="ingestion",
    soft_time_limit=300,
    time_limit=360,
    max_retries=3,
    autoretry_for=(GithubRateLimitError, GithubRetryableError),
    retry_backoff=60,
    retry_backoff_max=300,
)
def fetch_builds_batch(
    self: PipelineTask,
    repo_config_id: str,
    ci_provider: str,
    page: int,
    batch_size: int,
    import_version: int,
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
    asyncio.set_event_loop(loop)
    try:
        builds = loop.run_until_complete(ci_instance.fetch_builds(full_name, **fetch_kwargs))
    finally:
        loop.close()

    if not builds:
        logger.info(f"{log_ctx} No builds found")
        return {"page": page, "builds": 0, "has_more": False}

    # Save builds and create ModelImportBuild records
    import_builds_to_insert = []
    for build in builds:
        if build.status != BuildStatus.COMPLETED:
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
            commit_message=None,
            commit_author=None,
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

        # Check if ModelImportBuild already exists for this import version
        existing = import_build_repo.find_by_business_key(repo_config_id, str(raw_build_run.id))
        if existing and existing.import_version == import_version:
            continue  # Already created

        # Create ModelImportBuild
        import_build = ModelImportBuild(
            model_repo_config_id=ObjectId(repo_config_id),
            raw_build_run_id=raw_build_run.id,
            import_version=import_version,
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
    import_version: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Aggregate fetch results and dispatch ingestion.

    Queries DB for all PENDING builds instead of passing state.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[aggregate_fetch]"

    import_build_repo = ModelImportBuildRepository(self.db)
    repo_config_repo = ModelRepoConfigRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    # Query DB for fetched builds
    fetched_builds = import_build_repo.find_fetched_builds(
        repo_config_id, import_version=import_version
    )

    total_fetched = len(fetched_builds)
    logger.info(f"{log_ctx} Found {total_fetched} fetched builds in DB")

    if total_fetched == 0:
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "import_status": ModelImportStatus.IMPORTED.value,
                "total_builds_imported": 0,
            },
        )
        publish_status(repo_config_id, "imported", "No builds found")
        return {"status": "completed", "builds": 0}

    # Update repo config
    repo_config = repo_config_repo.find_by_id(repo_config_id)
    repo_config_repo.update_repository(
        repo_config_id,
        {"total_builds_imported": total_fetched},
    )

    # Get commit SHAs and CI run IDs from fetched builds
    commit_shas = import_build_repo.get_commit_shas(repo_config_id, import_version)
    ci_run_ids = import_build_repo.get_ci_run_ids(repo_config_id, import_version)

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
        import_version=import_version,
        correlation_id=correlation_id,
    )

    publish_status(
        repo_config_id,
        "importing",
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
    import_version: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Build and dispatch ingestion workflow.

    After ingestion completes, dispatches processing.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[dispatch_ingestion]"

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

    # Build callback chain
    callback_chain = celery_chain(
        aggregate_model_ingestion_results.s(
            repo_config_id=repo_config_id,
            import_version=import_version,
            correlation_id=correlation_id,
        ),
        dispatch_processing_from_db.si(
            repo_config_id=repo_config_id,
            import_version=import_version,
        ),
    )

    if ingestion_workflow:
        logger.info(f"{log_ctx} Dispatching ingestion chord -> processing")
        chord(ingestion_workflow, callback_chain).apply_async()
    else:
        logger.info(f"{log_ctx} No ingestion needed, dispatching processing")
        callback_chain.apply_async()

    return {"status": "dispatched", "resources": list(required_resources)}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.aggregate_model_ingestion_results",
    queue="ingestion",
    soft_time_limit=30,
)
def aggregate_model_ingestion_results(
    self: PipelineTask,
    results: Any,
    repo_config_id: str,
    import_version: int,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Chord callback after ingestion workflow completes.

    Simply logs completion and signals processing to start.
    (ModelImportBuild only tracks fetch status, not ingestion)
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    logger.info(f"{corr_prefix}[aggregate_ingestion] Ingestion completed")

    publish_status(
        repo_config_id,
        "processing",
        "Resources ready, starting feature extraction...",
    )

    return {"status": "completed"}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.dispatch_processing_from_db",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def dispatch_processing_from_db(
    self: PipelineTask,
    repo_config_id: str,
    import_version: int,
) -> Dict[str, Any]:
    """
    Query DB for fetched builds and dispatch processing.

    Uses ModelImportBuild.FETCHED status to find builds.
    """
    # Get correlation_id for propagation
    correlation_id = TracingContext.get_correlation_id()

    import_build_repo = ModelImportBuildRepository(self.db)

    # Query FETCHED builds from DB
    fetched_builds = import_build_repo.find_fetched_builds(repo_config_id, import_version)

    if not fetched_builds:
        logger.info(f"No fetched builds for {repo_config_id}")
        return {"status": "completed", "builds": 0}

    # Extract raw_build_run_ids
    raw_build_run_ids = [str(b.raw_build_run_id) for b in fetched_builds]

    # Get raw_repo_id from config
    repo_config_repo = ModelRepoConfigRepository(self.db)
    repo_config = repo_config_repo.find_by_id(repo_config_id)

    # Dispatch processing with correlation_id
    dispatch_build_processing.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        raw_build_run_ids=raw_build_run_ids,
        correlation_id=correlation_id,
    )

    logger.info(f"Dispatched processing for {len(raw_build_run_ids)} builds")

    return {"status": "dispatched", "builds": len(raw_build_run_ids)}
