"""
Model Ingestion Tasks - Chain-based workflow for importing repositories.

This module implements a clean, chain-based Celery workflow:
1. import_repo - Orchestrator that starts the chain
2. clone_repo - Clone/update the git repository
3. fetch_and_save_builds - Fetch builds from CI provider and save to DB
4. dispatch_processing - Schedule feature extraction in batches
"""

from app.repositories.raw_repository import RawRepositoryRepository
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from pathlib import Path

from bson import ObjectId
from celery import chain, group
import redis
import json
import subprocess

from app.celery_app import celery_app
from app.config import settings
from app.tasks.base import PipelineTask
from app.entities.enums import ExtractionStatus, ModelImportStatus
from app.entities.raw_build_run import RawBuildRun
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.ci_providers import CIProvider, get_provider_config, get_ci_provider
from app.ci_providers.models import BuildStatus, BuildConclusion
from app.services.github.exceptions import GithubRateLimitError
from app.paths import REPOS_DIR, LOGS_DIR, WORKTREES_DIR
from app.pipeline.feature_dag._metadata import (
    get_required_resources_for_features,
    get_ingestion_tasks_for_resources,
    FeatureResource,
)
from app.repositories.dataset_template_repository import DatasetTemplateRepository

logger = logging.getLogger(__name__)


def get_redis_client():
    """Get Redis client for publishing events."""
    return redis.from_url(settings.REDIS_URL)


def publish_status(repo_id: str, status: str, message: str = ""):
    """Publish status update to Redis for real-time UI updates."""
    try:
        redis_client = get_redis_client()
        redis_client.publish(
            "events",
            json.dumps(
                {
                    "type": "REPO_UPDATE",
                    "payload": {
                        "repo_id": repo_id,
                        "status": status,
                        "message": message,
                    },
                }
            ),
        )
    except Exception as e:
        logger.error(f"Failed to publish status update: {e}")


def get_required_resources_for_template(
    db, template_name: str = "TravisTorrent Full"
) -> set:
    template_repo = DatasetTemplateRepository(db)
    template = template_repo.find_by_name(template_name)
    if template and template.feature_names:
        feature_set = set(template.feature_names)
        return get_required_resources_for_features(feature_set)
    return {r.value for r in FeatureResource}


# Task 1: import_repo - Orchestrator


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.import_repo",
    queue="import_repo",
)
def import_repo(
    self: PipelineTask,
    user_id: str,
    full_name: str,
    installation_id: str,
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator task - kicks off the import chain.

    Chain: clone_repo -> fetch_and_save_builds -> dispatch_processing
    """
    model_repo_repo = ModelRepoConfigRepository(self.db)

    try:
        # Find existing repo config
        repo = model_repo_repo.find_one(
            {
                "user_id": ObjectId(user_id),
                "provider": "github",
                "full_name": full_name,
            }
        )

        if not repo:
            raise ValueError(
                "ModelRepoConfig not found. Create it via RepositoryService first."
            )

        repo_id = str(repo.id)
        model_repo_repo.update_repository(
            repo_id,
            {
                "import_status": ModelImportStatus.IMPORTING.value,
                "installation_id": installation_id,
                "ci_provider": ci_provider,
            },
        )

        publish_status(repo_id, "importing", "Starting import workflow...")

        # Determine required resources based on template
        required_resources = get_required_resources_for_template(self.db)

        # Get ordered ingestion tasks for required resources
        ingestion_tasks = get_ingestion_tasks_for_resources(required_resources)

        logger.info(
            f"Required resources for {full_name}: {required_resources}. "
            f"Ingestion tasks: {ingestion_tasks}"
        )

        # Build chain dynamically
        # Always: fetch_builds (mandatory for getting build info)
        tasks = [
            fetch_and_save_builds.s(
                repo_id=repo_id,
                full_name=full_name,
                installation_id=installation_id,
                ci_provider=ci_provider,
                max_builds=max_builds,
                since_days=since_days,
                only_with_logs=only_with_logs,
            ),
        ]

        # Add ingestion tasks in dependency order
        for task_name in ingestion_tasks:
            if task_name == "clone_repo":
                # Insert clone_repo at beginning (before fetch_builds needs it for GIT_HISTORY)
                tasks.insert(0, clone_repo.s(repo_id, full_name, installation_id))
            elif task_name == "download_build_logs":
                tasks.append(
                    download_build_logs.s(
                        repo_id=repo_id,
                        full_name=full_name,
                        installation_id=installation_id,
                        ci_provider=ci_provider,
                    )
                )
            elif task_name == "create_worktrees_batch":
                tasks.append(create_worktrees_batch.s(repo_id=repo_id))

        tasks.append(dispatch_processing.s(repo_id=repo_id))

        workflow = chain(*tasks)
        workflow.apply_async()

        return {
            "status": "queued",
            "repo_id": repo_id,
            "message": "Import workflow started",
        }

    except Exception as e:
        logger.error(f"Failed to start import for {full_name}: {e}")
        if "repo_id" in locals():
            model_repo_repo.update_repository(
                repo_id,
                {
                    "import_status": ModelImportStatus.FAILED.value,
                    "last_sync_error": str(e),
                },
            )
            publish_status(repo_id, "failed", str(e))
        raise


# Task 2: clone_repo - Clone/update git repository
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.clone_repo",
    queue="import_repo",
    autoretry_for=(subprocess.CalledProcessError,),
    retry_kwargs={"max_retries": 3, "countdown": 360},
)
def clone_repo(
    self: PipelineTask,
    repo_id: str,
    full_name: str,
    installation_id: str,
) -> Dict[str, Any]:
    """
    Clone or update the git repository.

    Returns repo_id for chaining.
    """
    publish_status(repo_id, "importing", "Cloning repository...")

    repo_path = REPOS_DIR / repo_id

    try:
        if repo_path.exists():
            # Update existing clone
            logger.info(f"Updating existing clone for {full_name}")
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=300,
            )
        else:
            # Clone new repo
            logger.info(f"Cloning {full_name} to {repo_path}")
            clone_url = f"https://github.com/{full_name}.git"

            # For private repos, we need to use the installation token
            if installation_id:
                from app.services.github.github_app import get_installation_token

                token = get_installation_token(installation_id, self.db)
                clone_url = f"https://x-access-token:{token}@github.com/{full_name}.git"

            subprocess.run(
                ["git", "clone", "--bare", clone_url, str(repo_path)],
                check=True,
                capture_output=True,
                timeout=600,
            )

        publish_status(repo_id, "importing", "Repository cloned successfully")
        return {"repo_id": repo_id, "status": "cloned"}

    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed for {full_name}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Failed to clone {full_name}: {e}")
        raise


# Task 3: fetch_and_save_builds - Fetch from CI and save to DB


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.fetch_and_save_builds",
    queue="import_repo",
    autoretry_for=(GithubRateLimitError,),
    retry_kwargs={"max_retries": 5},
)
def fetch_and_save_builds(
    self: PipelineTask,
    clone_result: Dict[str, Any],  # Result from clone_repo
    repo_id: str,
    full_name: str,
    installation_id: str,
    ci_provider: str,
    max_builds: Optional[int] = None,
    since_days: Optional[int] = None,
    only_with_logs: bool = False,
) -> Dict[str, Any]:
    """
    Fetch builds from CI provider and save to database in batches.
    """
    publish_status(repo_id, "importing", "Fetching builds from CI provider...")

    model_repo_repo = ModelRepoConfigRepository(self.db)
    build_run_repo = RawBuildRunRepository(self.db)
    model_build_repo = ModelTrainingBuildRepository(self.db)

    since_dt = None
    if since_days:
        since_dt = datetime.now(timezone.utc) - timedelta(days=since_days)

    batch_size = settings.PROCESSING_BATCH_SIZE

    try:
        # Get CI provider instance
        ci_provider_enum = CIProvider(ci_provider)
        provider_config = get_provider_config(ci_provider_enum)
        ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

        # Fetch builds with internal pagination (CI provider handles per_page)
        fetch_kwargs = {
            "since": since_dt,
            "limit": max_builds,
            "exclude_bots": True,
            "only_with_logs": only_with_logs,
        }
        if ci_provider_enum == CIProvider.GITHUB_ACTIONS and installation_id:
            fetch_kwargs["installation_id"] = installation_id

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            builds = loop.run_until_complete(
                ci_instance.fetch_builds(full_name, **fetch_kwargs)
            )
        finally:
            loop.close()

        total_fetched = len(builds)
        logger.info(
            f"Fetched {total_fetched} builds from {ci_provider} for {full_name}"
        )
        publish_status(
            repo_id, "importing", f"Found {total_fetched} builds, saving in batches..."
        )

        # Process and save builds in batches
        saved_count = 0
        build_ids = []

        for batch_start in range(0, len(builds), batch_size):
            batch_end = min(batch_start + batch_size, len(builds))
            batch = builds[batch_start:batch_end]
            batch_saved = 0

            for build in batch:
                if build.status != BuildStatus.COMPLETED:
                    continue

                run_id = build.build_id

                # Check if already exists
                build_run = build_run_repo.find_by_repo_and_build_id(repo_id, run_id)

                if not build_run:
                    build_run = RawBuildRun(
                        _id=None,
                        raw_repo_id=ObjectId(repo_id),
                        build_id=run_id,
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
                        logs_available=False,
                        logs_path=None,
                        provider=ci_provider_enum,
                        raw_data=build.raw_data or {},
                        is_bot_commit=False,
                    )
                    build_run = build_run_repo.insert_one(build_run)
                    batch_saved += 1

                # Check if ModelTrainingBuild already exists
                existing_model_build = model_build_repo.find_by_workflow_run(
                    ObjectId(repo_id), build_run.id
                )

                if not existing_model_build:
                    model_build = ModelTrainingBuild(
                        _id=None,
                        raw_repo_id=ObjectId(repo_id),
                        raw_workflow_run_id=build_run.id,
                        model_repo_config_id=ObjectId(repo_id),
                        head_sha=build.commit_sha,
                        build_number=build.build_number,
                        build_created_at=build.created_at,
                        build_conclusion=build.conclusion or BuildConclusion.UNKNOWN,
                        extraction_status=ExtractionStatus.PENDING,
                    )
                    model_build_repo.insert_one(model_build)

                build_ids.append(build_run.build_id)

            saved_count += batch_saved

            # Progress update after each batch
            publish_status(
                repo_id,
                "importing",
                f"Saved builds: {batch_end}/{total_fetched} ({saved_count} new)",
            )

        # Update repo with build count
        model_repo_repo.update_repository(
            repo_id,
            {
                "total_builds_imported": model_build_repo.count_by_repo_id(repo_id),
                "last_synced_at": datetime.now(timezone.utc),
            },
        )

        publish_status(repo_id, "importing", f"Saved {saved_count} new builds")

        return {
            "repo_id": repo_id,
            "builds_saved": saved_count,
            "total_builds": len(build_ids),
            "build_ids": build_ids,
        }

    except GithubRateLimitError as e:
        wait = e.retry_after if e.retry_after else 60
        logger.warning(f"Rate limit hit. Retrying in {wait}s")
        raise self.retry(countdown=wait)
    except Exception as e:
        logger.error(f"Failed to fetch builds for {full_name}: {e}")
        raise


# Task 4: download_build_logs - Download logs for builds (conditional)
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.download_build_logs",
    queue="import_repo",
    autoretry_for=(GithubRateLimitError,),
    retry_kwargs={"max_retries": 3},
)
def download_build_logs(
    self: PipelineTask,
    prev_result: Dict[str, Any],  # Result from previous task
    repo_id: str,
    full_name: str,
    installation_id: str,
    ci_provider: str,
) -> Dict[str, Any]:
    """
    Download build job logs from CI provider.

    Downloads all available logs, handling expired logs gracefully.
    GitHub Actions retains logs for 90 days by default.
    """
    import asyncio
    from app.services.github.exceptions import GithubLogsUnavailableError

    build_ids = prev_result.get("build_ids", [])

    if not build_ids:
        return {**prev_result, "logs_downloaded": 0, "logs_expired": 0}

    publish_status(
        repo_id, "importing", f"Downloading logs for {len(build_ids)} builds..."
    )

    build_run_repo = RawBuildRunRepository(self.db)

    # Get CI provider instance
    ci_provider_enum = CIProvider(ci_provider)
    provider_config = get_provider_config(ci_provider_enum)
    ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

    logs_downloaded = 0
    logs_expired = 0
    logs_skipped = 0
    max_log_size = settings.MAX_LOG_SIZE_MB * 1024 * 1024  # Convert to bytes

    async def download_logs_for_build(build_id: str) -> str:
        """
        Download logs for a single build.

        Returns:
            "downloaded" - logs saved successfully
            "expired" - logs no longer available (retention expired)
            "skipped" - logs already downloaded
            "failed" - other error
        """
        nonlocal logs_downloaded, logs_expired, logs_skipped

        # Check if logs already downloaded
        build_run = build_run_repo.find_by_repo_and_build_id(repo_id, build_id)
        if build_run and build_run.logs_available:
            logs_skipped += 1
            return "skipped"

        try:
            # Create build-specific logs directory
            build_logs_dir = LOGS_DIR / repo_id / build_id
            build_logs_dir.mkdir(parents=True, exist_ok=True)

            # Compose build_id in format expected by provider (repo_name:build_id)
            composite_id = f"{full_name}:{build_id}"

            # Pass installation_id for GitHub
            fetch_kwargs = {"build_id": composite_id}
            if ci_provider_enum == CIProvider.GITHUB_ACTIONS and installation_id:
                fetch_kwargs["installation_id"] = installation_id

            log_files = await ci_instance.fetch_build_logs(**fetch_kwargs)

            # No logs returned - likely expired
            if not log_files:
                if build_run:
                    build_run_repo.update_one(
                        str(build_run.id),
                        {"logs_available": False, "logs_expired": True},
                    )
                logs_expired += 1
                return "expired"

            saved_files = []
            for log_file in log_files:
                # Skip logs that are too large
                if log_file.size_bytes > max_log_size:
                    logger.warning(
                        f"Skipping log {log_file.path} ({log_file.size_bytes} bytes) - exceeds limit"
                    )
                    continue

                # Save log to file
                log_path = build_logs_dir / f"{log_file.job_name}.log"
                log_path.write_text(log_file.content)
                saved_files.append(str(log_path))

            if saved_files:
                # Update RawBuildRun with logs info
                if build_run:
                    build_run_repo.update_one(
                        str(build_run.id),
                        {
                            "logs_path": str(build_logs_dir),
                            "logs_available": True,
                            "logs_expired": False,
                        },
                    )
                logs_downloaded += 1
                return "downloaded"
            else:
                logs_expired += 1
                return "expired"

        except GithubLogsUnavailableError as e:
            # Logs expired or unavailable
            logger.info(f"Logs unavailable for build {build_id}: {e.reason}")
            if build_run:
                build_run_repo.update_one(
                    str(build_run.id),
                    {"logs_available": False, "logs_expired": True},
                )
            logs_expired += 1
            return "expired"
        except Exception as e:
            logger.warning(f"Failed to download logs for build {build_id}: {e}")
            return "failed"

    # Run async downloads for ALL builds
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Process all builds, but stop if all remaining are expired
        consecutive_expired = 0
        MAX_CONSECUTIVE_EXPIRED = 10  # Stop if 10 consecutive builds have expired logs
        batch_size = settings.DOWNLOAD_LOGS_BATCH_SIZE

        for i, build_id in enumerate(build_ids):
            result = loop.run_until_complete(download_logs_for_build(build_id))

            if result == "expired":
                consecutive_expired += 1
                # If many consecutive builds have expired logs, older builds likely expired too
                if consecutive_expired >= MAX_CONSECUTIVE_EXPIRED:
                    logger.info(
                        f"Stopping log download: {consecutive_expired} consecutive expired logs. "
                        f"Remaining {len(build_ids) - i - 1} builds likely expired too."
                    )
                    logs_expired += len(build_ids) - i - 1
                    break
            else:
                consecutive_expired = 0

            # Progress update every batch_size builds
            if (i + 1) % batch_size == 0:
                publish_status(
                    repo_id,
                    "importing",
                    f"Downloaded logs: {logs_downloaded}/{i+1} ({logs_expired} expired)",
                )
    finally:
        loop.close()

    publish_status(
        repo_id,
        "importing",
        f"Logs: {logs_downloaded} downloaded, {logs_expired} expired, {logs_skipped} skipped",
    )

    return {
        **prev_result,
        "logs_downloaded": logs_downloaded,
        "logs_expired": logs_expired,
        "logs_skipped": logs_skipped,
    }


# Task 5: create_worktrees_batch - Pre-create git worktrees for all builds
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.create_worktrees_batch",
    queue="import_repo",
)
def create_worktrees_batch(
    self: PipelineTask,
    prev_result: Dict[str, Any],  # Result from previous task
    repo_id: str,
) -> Dict[str, Any]:
    """
    Pre-create git worktrees for all builds that need them.

    This batches the worktree creation during ingestion instead of
    creating them one-by-one during processing.

    Also handles fork commits by replaying them and saving effective_sha to DB.
    """
    build_ids = prev_result.get("build_ids", [])

    if not build_ids:
        return {**prev_result, "worktrees_created": 0}

    publish_status(
        repo_id, "importing", f"Creating worktrees for {len(build_ids)} builds..."
    )

    build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)
    raw_repo = raw_repo_repo.find_by_id(repo_id)

    repo_path = REPOS_DIR / repo_id
    worktrees_dir = WORKTREES_DIR / repo_id
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    # Get GitHub client for fork commit replay
    github_client = None
    try:
        from app.services.github.github_client import get_public_github_client

        github_client = get_public_github_client()
    except Exception as e:
        logger.warning(f"Failed to get GitHub client for fork replay: {e}")

    # Prune stale worktrees first
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_path),
            capture_output=True,
            check=False,
            timeout=60,
        )
    except Exception as e:
        logger.warning(f"Failed to prune worktrees: {e}")

    worktrees_created = 0
    worktrees_skipped = 0
    worktrees_failed = 0
    fork_commits_replayed = 0

    # Track unique commit SHAs to avoid duplicating worktrees
    commit_shas_seen = set()

    for i, build_id in enumerate(build_ids):
        build_run = build_run_repo.find_by_repo_and_build_id(repo_id, str(build_id))
        if not build_run:
            continue

        commit_sha = build_run.commit_sha
        if not commit_sha:
            continue

        # Use effective_sha if already set (previously replayed)
        effective_sha = build_run.effective_sha or commit_sha

        # Skip if we already created worktree for this commit
        if effective_sha in commit_shas_seen:
            worktrees_skipped += 1
            continue
        commit_shas_seen.add(effective_sha)

        # Check if worktree already exists
        worktree_path = worktrees_dir / effective_sha[:12]
        if worktree_path.exists():
            worktrees_skipped += 1
            continue

        try:
            # Check if commit exists in repo
            result = subprocess.run(
                ["git", "cat-file", "-e", effective_sha],
                cwd=str(repo_path),
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                # Commit not available - attempt to replay fork commit
                if github_client and raw_repo:
                    try:
                        from app.services.commit_replay import ensure_commit_exists

                        synthetic_sha = ensure_commit_exists(
                            repo_path=repo_path,
                            commit_sha=commit_sha,
                            repo_slug=raw_repo.full_name,
                            github_client=github_client,
                        )
                        if synthetic_sha:
                            # Save effective_sha to DB
                            build_run_repo.update_effective_sha(
                                build_run.id, synthetic_sha
                            )
                            effective_sha = synthetic_sha
                            fork_commits_replayed += 1
                            logger.info(
                                f"Replayed fork commit {commit_sha[:8]} -> {synthetic_sha[:8]}"
                            )
                        else:
                            worktrees_skipped += 1
                            continue
                    except Exception as e:
                        logger.warning(
                            f"Failed to replay fork commit {commit_sha[:8]}: {e}"
                        )
                        worktrees_skipped += 1
                        continue
                else:
                    worktrees_skipped += 1
                    continue

            # Create worktree
            worktree_path = worktrees_dir / effective_sha[:12]
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree_path),
                    effective_sha,
                ],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=60,
            )
            worktrees_created += 1

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to create worktree for {effective_sha[:8]}: {e}")
            worktrees_failed += 1
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout creating worktree for {effective_sha[:8]}")
            worktrees_failed += 1

        # Progress update every 50 builds
        if (i + 1) % 50 == 0:
            publish_status(
                repo_id,
                "importing",
                f"Worktrees: {worktrees_created} created, {worktrees_skipped} skipped",
            )

    publish_status(
        repo_id,
        "importing",
        f"Worktrees: {worktrees_created} created, {fork_commits_replayed} replayed, {worktrees_failed} failed",
    )

    return {
        **prev_result,
        "worktrees_created": worktrees_created,
        "worktrees_skipped": worktrees_skipped,
        "worktrees_failed": worktrees_failed,
        "fork_commits_replayed": fork_commits_replayed,
    }


# Task 6: dispatch_processing - Schedule feature extraction in batches
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.model_ingestion.dispatch_processing",
    queue="import_repo",
)
def dispatch_processing(
    self: PipelineTask,
    fetch_result: Dict[str, Any],  # Result from fetch_and_save_builds
    repo_id: str,
    batch_size: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Dispatch feature extraction tasks in batches.
    This prevents flooding the queue with thousands of tasks at once.
    """
    import time

    # Use config default if not specified
    if batch_size is None:
        batch_size = settings.PROCESSING_BATCH_SIZE

    build_ids = fetch_result.get("build_ids", [])

    if not build_ids:
        logger.info(f"No builds to process for repo {repo_id}")

        # Mark as imported anyway
        model_repo_repo = ModelRepoConfigRepository(self.db)
        model_repo_repo.update_repository(
            repo_id,
            {
                "import_status": ModelImportStatus.IMPORTED.value,
            },
        )
        publish_status(repo_id, "imported", "No new builds to process")

        return {"repo_id": repo_id, "dispatched": 0}

    publish_status(
        repo_id, "importing", f"Scheduling {len(build_ids)} builds for processing..."
    )

    dispatched = 0

    # Process in batches
    for i in range(0, len(build_ids), batch_size):
        batch = build_ids[i : i + batch_size]

        # Create a group of tasks for this batch
        tasks = group(
            [
                celery_app.signature(
                    "app.tasks.processing.process_workflow_run",
                    args=[repo_id, build_id],
                )
                for build_id in batch
            ]
        )
        tasks.apply_async()

        dispatched += len(batch)
        logger.info(f"Dispatched batch {i // batch_size + 1}: {len(batch)} tasks")

        if i + batch_size < len(build_ids):
            time.sleep(0.05)

    # Mark import as complete
    model_repo_repo = ModelRepoConfigRepository(self.db)
    model_repo_repo.update_repository(
        repo_id,
        {
            "import_status": ModelImportStatus.IMPORTED.value,
            "last_sync_status": "success",
        },
    )

    publish_status(
        repo_id, "imported", f"Dispatched {dispatched} builds for processing"
    )

    return {
        "repo_id": repo_id,
        "dispatched": dispatched,
        "status": "completed",
    }
