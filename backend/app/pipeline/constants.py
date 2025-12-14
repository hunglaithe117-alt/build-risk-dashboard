from app.pipeline.feature_dag import (
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
