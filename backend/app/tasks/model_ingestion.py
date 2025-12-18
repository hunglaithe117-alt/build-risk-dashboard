"""
Model Ingestion Tasks - Resource preparation for model training builds.

This module uses chain-based task pattern for fetching builds:
1. ingest_model_builds - Orchestrator: Dispatches first batch
2. fetch_builds_batch - Fetches one page, saves to DB, chains to next page
3. prepare_and_dispatch_processing - Prepares resources and dispatches processing

Flow:
  ingest_model_builds → fetch_builds_batch(page=1) → fetch_builds_batch(page=2) → ... → prepare_and_dispatch_processing
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.celery_app import celery_app
from app.tasks.base import PipelineTask
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.ci_providers import CIProvider, get_provider_config, get_ci_provider
from app.services.github.exceptions import GithubRateLimitError, GithubRetryableError
from app.tasks.pipeline.feature_dag._metadata import (
    get_required_resources_for_features,
    FeatureResource,
)
from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
from app.tasks.shared import build_ingestion_workflow
from app.ci_providers.models import BuildStatus
from app.tasks.model_processing import publish_status

logger = logging.getLogger(__name__)

# Default batch size for fetching builds
DEFAULT_BATCH_SIZE = 50


def get_required_resources_for_template(
    db, template_name: str = "TravisTorrent Full"
) -> set:
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
    soft_time_limit=60,
    time_limit=120,
)
def ingest_model_builds(
    self: PipelineTask,
    repo_config_id: str,
    ci_provider: str,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """
    Orchestrator: Dispatch first batch fetch task.

    This task validates the repo config and dispatches the first page fetch.
    Subsequent pages are fetched via chained tasks.
    """
    repo_config_repo = ModelRepoConfigRepository(self.db)
    repo_config = repo_config_repo.find_by_id(repo_config_id)

    if not repo_config:
        raise ValueError(f"ModelRepoConfig {repo_config_id} not found")

    # Dispatch first batch (page 1)
    fetch_builds_batch.delay(
        repo_config_id=repo_config_id,
        raw_repo_id=str(repo_config.raw_repo_id),
        full_name=repo_config.full_name,
        ci_provider=ci_provider,
        max_builds=max_builds,
        since_days=since_days,
        only_with_logs=only_with_logs,
        batch_size=batch_size,
        page=1,
        total_fetched=0,
        ci_build_ids=[],
    )

    return {
        "status": "dispatched",
        "repo_config_id": repo_config_id,
        "message": "First batch fetch dispatched",
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.fetch_builds_batch",
    queue="ingestion",
    soft_time_limit=300,
    time_limit=360,
    autoretry_for=(GithubRateLimitError, GithubRetryableError),
    retry_backoff=60,
    max_retries=5,
)
def fetch_builds_batch(
    self: PipelineTask,
    repo_config_id: str,
    raw_repo_id: str,
    full_name: str,
    ci_provider: str,
    page: int,
    total_fetched: int,
    ci_build_ids: List[str],
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Dict[str, Any]:
    """
    Fetch a single page of builds, save to DB, and chain to next page or finalize.

    This task:
    1. Fetches one page from CI provider
    2. Saves builds to RawBuildRun collection
    3. Chains to next page OR prepare_and_dispatch_processing
    """
    import asyncio

    build_run_repo = RawBuildRunRepository(self.db)

    since_dt = None
    if since_days:
        since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)

    try:
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

        # Fetch single page
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            builds = loop.run_until_complete(
                ci_instance.fetch_builds(full_name, **fetch_kwargs)
            )
        finally:
            loop.close()

        # Process and save builds
        batch_ci_build_ids = []
        for build in builds:
            if build.status != BuildStatus.COMPLETED:
                continue

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
            batch_ci_build_ids.append(raw_build_run.build_id)

            # Check max builds limit
            if max_builds and (total_fetched + len(batch_ci_build_ids)) >= max_builds:
                break

        # Accumulate build IDs
        new_total = total_fetched + len(batch_ci_build_ids)
        new_ci_build_ids = ci_build_ids + batch_ci_build_ids

        logger.info(
            f"Page {page}: saved {len(batch_ci_build_ids)} builds for {full_name} "
            f"(total: {new_total})"
        )

        # Determine next action
        has_more = len(builds) >= batch_size
        reached_limit = max_builds and new_total >= max_builds

        if has_more and not reached_limit:
            # Chain to next page
            fetch_builds_batch.delay(
                repo_config_id=repo_config_id,
                raw_repo_id=raw_repo_id,
                full_name=full_name,
                ci_provider=ci_provider,
                page=page + 1,
                total_fetched=new_total,
                ci_build_ids=new_ci_build_ids,
                max_builds=max_builds,
                since_days=since_days,
                only_with_logs=only_with_logs,
                batch_size=batch_size,
            )
            return {
                "status": "chained",
                "page": page,
                "builds_this_page": len(batch_ci_build_ids),
                "total_so_far": new_total,
                "next_page": page + 1,
            }
        else:
            prepare_and_dispatch_processing.delay(
                repo_config_id=repo_config_id,
                raw_repo_id=raw_repo_id,
                full_name=full_name,
                ci_provider=ci_provider,
                ci_build_ids=new_ci_build_ids,
            )
            return {
                "status": "completed",
                "page": page,
                "builds_this_page": len(batch_ci_build_ids),
                "total_builds": new_total,
            }

    except GithubRateLimitError:
        logger.warning(f"Rate limit hit on page {page} for {full_name}, retrying...")
        raise
    except Exception as e:
        logger.error(f"Failed to fetch page {page} for {full_name}: {e}")
        from app.entities.enums import ModelImportStatus

        repo_config_repo = ModelRepoConfigRepository(self.db)
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "import_status": ModelImportStatus.FAILED.value,
                "last_sync_status": "failed",
                "last_sync_error": str(e),
            },
        )
        publish_status(repo_config_id, "failed", str(e))
        raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.prepare_and_dispatch_processing",
    queue="ingestion",
    soft_time_limit=300,
    time_limit=360,
)
def prepare_and_dispatch_processing(
    self: PipelineTask,
    repo_config_id: str,
    raw_repo_id: str,
    full_name: str,
    ci_provider: str,
    ci_build_ids: List[str],
) -> Dict[str, Any]:
    """
    Final step: Build ingestion workflow and dispatch processing.

    This task:
    1. Collects raw_build_run ObjectIds from ci_build_ids
    2. Gets commit SHAs for worktree creation
    3. Builds and applies ingestion workflow (clone, logs, worktrees)
    4. Dispatches dispatch_build_processing for feature extraction
    """
    from app.tasks.model_processing import dispatch_build_processing

    if not ci_build_ids:
        logger.info(f"No builds to process for {full_name}")
        from app.entities.enums import ModelImportStatus

        repo_config_repo = ModelRepoConfigRepository(self.db)
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "import_status": ModelImportStatus.IMPORTED.value,
                "last_sync_status": "success",
                "last_sync_error": None,
            },
        )
        publish_status(repo_config_id, "imported", "No builds found")
        return {"status": "completed", "builds": 0, "message": "No builds found"}

    try:
        raw_build_run_repo = RawBuildRunRepository(self.db)
        ci_provider_enum = CIProvider(ci_provider)

        raw_build_docs = raw_build_run_repo.find_ids_by_build_ids(
            ObjectId(raw_repo_id), ci_build_ids, ci_provider_enum.value
        )

        raw_build_run_ids = [str(doc["_id"]) for doc in raw_build_docs]
        commit_shas = list(
            set(
                doc.get("effective_sha") or doc.get("commit_sha")
                for doc in raw_build_docs
                if doc.get("commit_sha")
            )
        )

        logger.info(
            f"Finalizing ingestion for {full_name}: {len(raw_build_run_ids)} builds"
        )

        # Step 2: Determine required resources based on template
        required_resources = get_required_resources_for_template(self.db)
        tasks_by_level = get_ingestion_tasks_by_level(list(required_resources))

        # Debug logging for resource resolution
        logger.info(f"[DEBUG] Required resources: {sorted(required_resources)}")
        logger.info(f"[DEBUG] Tasks by level: {tasks_by_level}")
        logger.info(f"[DEBUG] Commit SHAs for worktrees: {commit_shas[:5]}...")

        template_repo = DatasetTemplateRepository(self.db)
        template = template_repo.find_by_name("TravisTorrent Full")
        feature_names = template.feature_names if template else []

        repo_config_repo = ModelRepoConfigRepository(self.db)
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "total_builds_imported": len(raw_build_run_ids),
                "feature_extractors": feature_names,
            },
        )

        # Step 3: Create processing task signature
        from app.tasks.model_processing import dispatch_build_processing

        final_task = dispatch_build_processing.si(
            repo_config_id=repo_config_id,
            raw_repo_id=raw_repo_id,
            raw_build_run_ids=raw_build_run_ids,
        )

        # Step 4: Build and execute workflow with processing as final task
        if tasks_by_level:
            workflow = build_ingestion_workflow(
                tasks_by_level=tasks_by_level,
                raw_repo_id=raw_repo_id,
                full_name=full_name,
                build_ids=ci_build_ids,
                commit_shas=commit_shas,
                ci_provider=ci_provider_enum.value,
                final_task=final_task,  # Processing runs AFTER ingestion
            )
            if workflow:
                workflow.apply_async()
            else:
                # No ingestion tasks, run processing directly
                final_task.apply_async()
        else:
            # No resources needed, run processing directly
            final_task.apply_async()

        return {
            "status": "dispatched",
            "raw_repo_id": raw_repo_id,
            "builds": len(ci_build_ids),
            "raw_build_run_ids": len(raw_build_run_ids),
            "resources": list(required_resources) if tasks_by_level else [],
        }

    except Exception as e:
        logger.error(f"Failed to prepare/dispatch processing for {full_name}: {e}")
        from app.entities.enums import ModelImportStatus

        repo_config_repo = ModelRepoConfigRepository(self.db)
        repo_config_repo.update_repository(
            repo_config_id,
            {
                "import_status": ModelImportStatus.FAILED.value,
                "last_sync_status": "failed",
                "last_sync_error": str(e),
            },
        )
        publish_status(repo_config_id, "failed", str(e))
        raise
