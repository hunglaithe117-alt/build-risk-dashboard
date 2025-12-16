"""
Shared Processing Helpers - Common feature extraction logic.

These helpers are used by both model_processing.py and enrichment_processing.py
to extract features using the Hamilton pipeline.
"""

from app.entities.repo_config_base import RepoConfigBase
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.entities.raw_build_run import RawBuildRun
from app.entities.raw_repository import RawRepository
from app.entities.pipeline_run import (
    PipelineRun,
    PipelineCategory,
    NodeExecutionResult,
    NodeExecutionStatus,
)
from app.repositories.pipeline_run import PipelineRunRepository
from app.tasks.pipeline.hamilton_runner import HamiltonPipeline
from app.tasks.pipeline.feature_dag._inputs import build_hamilton_inputs
from app.tasks.pipeline.feature_dag._metadata import format_features_for_storage
from app.paths import REPOS_DIR

logger = logging.getLogger(__name__)


def extract_features_for_build(
    db,
    raw_repo: RawRepository,
    repo_config: RepoConfigBase,  # Can be ModelRepoConfig or DatasetRepoConfig
    raw_build_run: RawBuildRun,
    selected_features: List[str] = [],
    github_client=None,
) -> Dict[str, Any]:
    """
    Extract features for a single build using HamiltonPipeline.

    Always returns a result dict containing:
    - status: "completed", "partial", or "failed"
    - features: Extracted features dict (formatted for storage)
    - feature_count: Number of features extracted
    - errors: List of error messages
    - warnings: List of warning messages
    - is_missing_commit: Whether the commit was missing from repo

    Args:
        db: Database session
        raw_repo: RawRepository entity
        repo_config: ModelRepoConfig or DatasetRepoConfig entity
        raw_build_run: RawBuildRun entity
        selected_features: Optional list of features to extract
        github_client: Optional GitHub client for API calls

    Returns:
        Dictionary with status, features, errors, warnings, etc.
    """
    repo_path = REPOS_DIR / str(raw_repo.id)

    try:
        # Build all Hamilton inputs using helper function
        inputs = build_hamilton_inputs(
            raw_repo=raw_repo,
            repo_config=repo_config,
            build_run=raw_build_run,
            repo_path=repo_path,
        )

        # Execute Hamilton pipeline
        pipeline = HamiltonPipeline(db=db)

        features = pipeline.run(
            git_history=inputs.git_history,
            git_worktree=inputs.git_worktree,
            repo=inputs.repo,
            build_run=inputs.build_run,
            repo_config=inputs.repo_config,
            github_client=github_client,
            features_filter=set(selected_features) if selected_features else None,
        )

        formatted_features = format_features_for_storage(features)

        result = {
            "status": "completed",
            "features": formatted_features,
            "feature_count": len(formatted_features),
            "errors": [],
            "warnings": [],
            "is_missing_commit": not inputs.is_commit_available,
        }

        if not inputs.is_commit_available:
            result["warnings"].append(
                f"Commit {raw_build_run.commit_sha} not found in repo"
            )

        return result

    except Exception as e:
        logger.error(
            f"Pipeline failed for build {raw_build_run.build_id}: {e}",
            exc_info=True,
        )
        return {
            "status": "failed",
            "features": {},
            "feature_count": 0,
            "errors": [str(e)],
            "warnings": [],
            "is_missing_commit": False,
        }
