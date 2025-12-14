"""
Dataset Ingestion Tasks - Resource preparation for dataset builds.

This module handles resource preparation (clone, worktree, logs) for dataset builds:
1. ingest_dataset_builds - Orchestrator
2. clone_dataset_repo - Clone/update git repository
3. create_dataset_worktrees - Create git worktrees for commits
4. download_dataset_logs - Download build job logs

Resources are prepared based on selected features to minimize unnecessary work.
"""

import logging
import asyncio
import subprocess
from typing import Any, Dict, List, Optional, Set

from celery import chain, group

from app.celery_app import celery_app
from app.config import settings
from app.tasks.base import PipelineTask
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.ci_providers import CIProvider, get_provider_config, get_ci_provider
from app.services.github.exceptions import GithubRateLimitError
from app.paths import REPOS_DIR, WORKTREES_DIR, LOGS_DIR

logger = logging.getLogger(__name__)


# Task 1: Orchestrator
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_ingestion.ingest_dataset_builds",
    queue="ingestion",
)
def ingest_dataset_builds(
    self: PipelineTask,
    dataset_id: str,
    repo_id: str,
    build_ids: List[str],
    features: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Orchestrate resource preparation for dataset builds.

    Chain: clone -> group([worktrees, logs]) based on required resources.
    """
    dataset_repo_config_repo = DatasetRepoConfigRepository(self.db)

    repo_config = dataset_repo_config_repo.find_by_id(repo_id)
    if not repo_config:
        raise ValueError(f"Dataset repo config {repo_id} not found")

    full_name = repo_config.normalized_full_name
    ci_provider = repo_config.ci_provider

    # Determine required resources
    feature_set = set(features) if features else None
    required = get_required_resources(feature_set)

    logger.info(f"Required resources for features: {required}")

    # Build chain based on required resources
    tasks = []

    # Always clone if git_history is needed
    if "git_history" in required:
        tasks.append(
            clone_dataset_repo.s(
                repo_id=repo_id,
                full_name=full_name,
            )
        )

    # Parallel tasks after clone
    parallel_tasks = []

    if "git_worktree" in required:
        # Get commit SHAs from builds
        build_run_repo = RawBuildRunRepository(self.db)
        commit_shas = []
        for build_id in build_ids:
            build = build_run_repo.find_by_repo_and_build_id(repo_id, build_id)
            if build and build.commit_sha:
                commit_shas.append(build.commit_sha)

        if commit_shas:
            parallel_tasks.append(
                create_dataset_worktrees.s(
                    repo_id=repo_id,
                    commit_shas=list(set(commit_shas)),
                )
            )

    if "build_logs" in required:
        parallel_tasks.append(
            download_dataset_logs.s(
                repo_id=repo_id,
                full_name=full_name,
                build_ids=build_ids,
                ci_provider=ci_provider,
            )
        )

    # Build workflow
    if parallel_tasks:
        if tasks:
            # Clone first, then parallel tasks
            workflow = chain(
                *tasks,
                group(*parallel_tasks),
            )
        else:
            # Just parallel tasks
            workflow = group(*parallel_tasks)
    elif tasks:
        workflow = chain(*tasks)
    else:
        # Nothing to do
        return {"status": "skipped", "reason": "No resources required"}

    workflow.apply_async()

    return {
        "status": "dispatched",
        "repo_id": repo_id,
        "builds": len(build_ids),
        "resources": list(required),
    }


# Task 2: Clone repository
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_ingestion.clone_dataset_repo",
    queue="ingestion",
    autoretry_for=(subprocess.CalledProcessError,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
)
def clone_dataset_repo(
    self: PipelineTask,
    repo_id: str,
    full_name: str,
) -> Dict[str, Any]:
    """Clone or update git repository for dataset."""
    repo_path = REPOS_DIR / repo_id

    try:
        if repo_path.exists():
            logger.info(f"Updating clone for {full_name}")
            subprocess.run(
                ["git", "fetch", "--all", "--prune"],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=300,
            )
        else:
            logger.info(f"Cloning {full_name} to {repo_path}")
            clone_url = f"https://github.com/{full_name}.git"
            subprocess.run(
                ["git", "clone", "--bare", clone_url, str(repo_path)],
                check=True,
                capture_output=True,
                timeout=600,
            )

        return {"repo_id": repo_id, "status": "cloned", "path": str(repo_path)}

    except subprocess.CalledProcessError as e:
        logger.error(f"Git operation failed for {full_name}: {e.stderr}")
        raise


# Task 3: Create worktrees
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_ingestion.create_dataset_worktrees",
    queue="ingestion",
)
def create_dataset_worktrees(
    self: PipelineTask,
    prev_result: Any,  # Result from previous task (can be dict or list)
    repo_id: str,
    commit_shas: List[str],
) -> Dict[str, Any]:
    """Create git worktrees for specified commits."""
    repo_path = REPOS_DIR / repo_id

    if not repo_path.exists():
        return {"repo_id": repo_id, "status": "error", "reason": "Repo not cloned"}

    created = 0
    failed = 0

    for sha in commit_shas:
        worktree_path = WORKTREES_DIR / repo_id / sha

        if worktree_path.exists():
            created += 1
            continue

        try:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=120,
            )
            created += 1
        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to create worktree for {sha}: {e.stderr}")
            failed += 1

    return {
        "repo_id": repo_id,
        "worktrees_created": created,
        "worktrees_failed": failed,
    }


# Task 4: Download logs
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_ingestion.download_dataset_logs",
    queue="ingestion",
    autoretry_for=(GithubRateLimitError,),
    retry_kwargs={"max_retries": 3},
)
def download_dataset_logs(
    self: PipelineTask,
    prev_result: Any,  # Result from previous task
    repo_id: str,
    full_name: str,
    build_ids: List[str],
    ci_provider: str,
) -> Dict[str, Any]:
    """Download build job logs from CI provider."""
    build_run_repo = RawBuildRunRepository(self.db)

    ci_provider_enum = CIProvider(ci_provider)
    provider_config = get_provider_config(ci_provider_enum)
    ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

    max_log_size = settings.MAX_LOG_SIZE_MB * 1024 * 1024
    logs_downloaded = 0

    async def download_logs_for_build(build_id: str):
        nonlocal logs_downloaded

        try:
            build_logs_dir = LOGS_DIR / repo_id / build_id
            build_logs_dir.mkdir(parents=True, exist_ok=True)

            composite_id = f"{full_name}:{build_id}"
            log_files = await ci_instance.fetch_build_logs(build_id=composite_id)

            saved = []
            for log_file in log_files:
                if log_file.size_bytes > max_log_size:
                    continue

                log_path = build_logs_dir / f"{log_file.job_name}.log"
                log_path.write_text(log_file.content)
                saved.append(str(log_path))

            if saved:
                build_run = build_run_repo.find_by_repo_and_build_id(repo_id, build_id)
                if build_run:
                    build_run_repo.update_one(
                        str(build_run.id),
                        {"logs_path": str(build_logs_dir), "logs_available": True},
                    )
                logs_downloaded += 1

        except Exception as e:
            logger.warning(f"Failed to download logs for build {build_id}: {e}")

    # Run downloads
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for build_id in build_ids[:50]:  # Limit batch size
            loop.run_until_complete(download_logs_for_build(build_id))
    finally:
        loop.close()

    return {"repo_id": repo_id, "logs_downloaded": logs_downloaded}
