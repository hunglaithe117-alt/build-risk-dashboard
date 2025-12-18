from app.tasks.pipeline.feature_dag import (
    build_features,
    git_features,
    github_features,
    log_features,
    repo_features,
)

DEFAULT_FEATURES = {"tr_build_id", "gh_project_name"}

HAMILTON_MODULES = [
    build_features,
    git_features,
    github_features,
    repo_features,
    log_features,
]

# Input resource names that should NOT be stored as features
# These are Hamilton DAG inputs, not actual feature values
# Must match the keys used in HamiltonPipeline.run() inputs dict
INPUT_RESOURCE_NAMES = frozenset(
    [
        "git_history",
        "git_worktree",
        "repo",
        "repo_config",
        "build_run",
        "github_client",
        "build_logs",
        "raw_build_runs",
    ]
)
