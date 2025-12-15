"""
Dataset Ingestion Tasks - Resource preparation for dataset builds.

This module uses shared ingestion infrastructure to prepare resources
(clone, worktree, logs) for dataset builds. It leverages resource_dag
to automatically determine which tasks are needed based on selected features.

Flow:
1. start_ingestion - Orchestrator: For each repo, dispatch ingest_dataset_builds
2. ingest_dataset_builds - Process a single repository (clone, worktree, logs)
"""

import logging
from typing import Any, Dict, List, Optional

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.entities import DatasetIngestionStatus
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.tasks.base import PipelineTask
from app.tasks.pipeline.feature_dag._metadata import get_required_resources_for_features
from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
from app.tasks.shared import build_ingestion_workflow
from app.utils.datetime import utc_now

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset_ingestion.start_ingestion",
    queue="ingestion",
    soft_time_limit=300,
    time_limit=360,
)
def start_ingestion(self: PipelineTask, dataset_id: str) -> Dict[str, Any]:
    """
    Orchestrator: Start ingestion for all repos in a dataset.

    For each validated repo, dispatches ingest_dataset_builds task.
    """
    db = get_database()
    dataset_repo = DatasetRepository(db)
    repo_config_repo = DatasetRepoConfigRepository(db)
    build_repo = DatasetBuildRepository(db)

    dataset = dataset_repo.find_by_id(dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {dataset_id} not found")

    # Mark as ingesting
    dataset_repo.update_one(
        dataset_id,
        {
            "ingestion_status": DatasetIngestionStatus.INGESTING,
            "ingestion_started_at": utc_now(),
            "ingestion_progress": 0,
            "ingestion_error": None,
        },
    )

    # Get all validated repos for this dataset
    repos = repo_config_repo.find_by_dataset(dataset_id)
    if not repos:
        dataset_repo.update_one(
            dataset_id,
            {
                "ingestion_status": DatasetIngestionStatus.COMPLETED,
                "ingestion_completed_at": utc_now(),
                "ingestion_progress": 100,
                "setup_step": 4,
            },
        )
        return {"status": "completed", "message": "No repos to ingest"}

    total_repos = len(repos)
    total_builds = 0

    # Update initial stats
    dataset_repo.update_one(
        dataset_id,
        {
            "ingestion_stats": {
                "repos_total": total_repos,
                "repos_ingested": 0,
                "repos_failed": 0,
                "builds_total": 0,
                "worktrees_created": 0,
                "logs_downloaded": 0,
            },
        },
    )

    # Dispatch ingestion for each repo
    for repo in repos:
        repo_id = str(repo.id)

        # Get validated builds for this repo
        builds = build_repo.find_by_repo(dataset_id, repo_id)
        build_ids = [str(b.build_id_from_csv) for b in builds if b.status == "found"]

        if not build_ids:
            continue

        total_builds += len(build_ids)

        # Dispatch per-repo ingestion
        ingest_dataset_builds.delay(
            dataset_id=dataset_id,
            repo_id=repo_id,
            build_ids=build_ids,
            features=None,  # Use all features
        )

    # Update total builds count
    dataset_repo.update_one(
        dataset_id,
        {"ingestion_stats.builds_total": total_builds},
    )

    logger.info(f"Dispatched ingestion for {total_repos} repos, {total_builds} builds")

    return {
        "status": "dispatched",
        "dataset_id": dataset_id,
        "repos": total_repos,
        "builds": total_builds,
    }


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

    Uses resource_dag to determine required ingestion tasks based on selected features.
    Tasks are grouped by level:
    - Level 0 tasks run first (e.g., clone_repo)
    - Level 1 tasks run after level 0, in parallel if multiple (e.g., worktrees, logs)
    """
    dataset_repo_config_repo = DatasetRepoConfigRepository(self.db)
    build_run_repo = RawBuildRunRepository(self.db)

    repo_config = dataset_repo_config_repo.find_by_id(repo_id)
    if not repo_config:
        raise ValueError(f"Dataset repo config {repo_id} not found")

    full_name = repo_config.normalized_full_name
    ci_provider = repo_config.ci_provider

    # Determine required resources using feature_dag metadata
    feature_set = set(features) if features else set()
    required_resources = get_required_resources_for_features(feature_set)

    # Get tasks grouped by level from resource_dag
    tasks_by_level = get_ingestion_tasks_by_level(list(required_resources))

    logger.info(
        f"Required resources: {required_resources}, tasks by level: {tasks_by_level}"
    )

    if not tasks_by_level:
        return {"status": "skipped", "reason": "No resources required"}

    # Get commit SHAs for worktree creation
    commit_shas = []
    for build_id in build_ids:
        build = build_run_repo.find_by_repo_and_build_id(repo_id, build_id)
        if build and build.commit_sha:
            commit_shas.append(build.effective_sha or build.commit_sha)
    commit_shas = list(set(commit_shas))

    # Build workflow using shared helper
    workflow = build_ingestion_workflow(
        tasks_by_level=tasks_by_level,
        repo_id=repo_id,
        full_name=full_name,
        build_ids=build_ids,
        commit_shas=commit_shas,
        ci_provider=ci_provider,
    )

    if not workflow:
        return {"status": "skipped", "reason": "No applicable tasks"}

    workflow.apply_async()

    return {
        "status": "dispatched",
        "repo_id": repo_id,
        "builds": len(build_ids),
        "resources": list(required_resources),
        "tasks_by_level": {str(k): v for k, v in tasks_by_level.items()},
    }
