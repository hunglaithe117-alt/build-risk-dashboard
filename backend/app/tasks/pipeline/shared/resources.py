from enum import Enum
from typing import Dict, List


class FeatureResource(str, Enum):
    """
    Resources required by features.

    Resources form a DAG with dependencies.
    """

    # Core inputs (always available from DB, no ingestion needed)
    BUILD_RUN = "build_run"  # Single RawBuildRun entity (current build)
    REPO = "repo"  # RawRepository metadata
    REPO_CONFIG = "repo_config"  # User-configured repo settings

    # Collection access
    RAW_BUILD_RUNS = "raw_build_runs"  # raw_build_runs collection

    # Git resources (require ingestion)
    GIT_HISTORY = "git_history"  # Git bare repo (clone_repo task)
    GIT_WORKTREE = "git_worktree"  # Git worktree (create_worktrees_batch task)

    # External resources
    GITHUB_API = "github_api"  # GitHub API client (on-demand, no ingestion)
    BUILD_LOGS = "build_logs"  # CI job logs (download_build_logs task)


# Task dependency graph
# Used to determine parallel execution order in Celery workflows
TASK_DEPENDENCIES: Dict[str, List[str]] = {
    "clone_repo": [],
    "fetch_and_save_builds": [],
    "create_worktrees_batch": ["clone_repo"],
    "download_build_logs": ["fetch_and_save_builds"],
}

# Resource → Leaf tasks only (dependencies resolved via TASK_DEPENDENCIES)
RESOURCE_LEAF_TASKS: Dict[FeatureResource, List[str]] = {
    FeatureResource.REPO: [],
    FeatureResource.REPO_CONFIG: [],
    FeatureResource.BUILD_RUN: ["fetch_and_save_builds"],
    FeatureResource.RAW_BUILD_RUNS: [],
    FeatureResource.GIT_HISTORY: ["clone_repo"],
    FeatureResource.GIT_WORKTREE: ["create_worktrees_batch"],
    FeatureResource.GITHUB_API: [],
    FeatureResource.BUILD_LOGS: ["download_build_logs"],
}

# Celery task paths
# Maps logical task names to their fully qualified Celery task names
INGESTION_TASK_TO_CELERY: Dict[str, str] = {
    "clone_repo": "app.tasks.shared.clone_repo",
    "fetch_and_save_builds": "app.tasks.model_ingestion.fetch_and_save_builds",
    "download_build_logs": "app.tasks.shared.download_build_logs",
    "create_worktrees_batch": "app.tasks.shared.create_worktrees_batch",
}
