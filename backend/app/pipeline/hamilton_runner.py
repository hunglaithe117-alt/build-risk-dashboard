"""
Hamilton-based feature pipeline runner.

This module provides the HamiltonPipeline class that executes
feature extraction using the Hamilton DAG framework.
"""

import logging
from typing import Any, Dict, Optional, Set

from hamilton import driver
from hamilton.execution.executors import SynchronousLocalTaskExecutor

from app.pipeline.hamilton_features import (
    build_features,
    git_features,
    github_features,
    repo_features,
)
from app.pipeline.hamilton_features._inputs import (
    GitHistoryInput,
    GitHubClientInput,
    GitWorktreeInput,
    RepoConfigInput,
    RepoInput,
    WorkflowRunInput,
)

logger = logging.getLogger(__name__)


class HamiltonPipeline:
    """
    Feature extraction using Hamilton DAG.

    Usage:
        pipeline = HamiltonPipeline(db)
        result = pipeline.run(
            git_history=GitHistoryInput(...),
            git_worktree=GitWorktreeInput(...),
            repo=RepoInput(...),
            workflow_run=WorkflowRunInput(...),
        )
    """

    def __init__(self, db: Any):
        """
        Initialize the Hamilton pipeline.

        Args:
            db: MongoDB database instance
        """
        self.db = db
        self._driver = self._build_driver()
        self._all_features = self._get_all_feature_names()

    def _build_driver(self) -> driver.Driver:
        """Build Hamilton driver with all feature modules."""
        return (
            driver.Builder()
            .with_modules(
                git_features,
                build_features,
                github_features,
                repo_features,
            )
            .with_local_executor(SynchronousLocalTaskExecutor())
            .build()
        )

    def _get_all_feature_names(self) -> Set[str]:
        """Get all available feature names."""
        return {v.name for v in self._driver.list_available_variables()}

    def get_active_features(self) -> Set[str]:
        """Get set of all active feature names."""
        return self._all_features.copy()

    def run(
        self,
        git_history: GitHistoryInput,
        git_worktree: GitWorktreeInput,
        repo: RepoInput,
        workflow_run: WorkflowRunInput,
        repo_config: Optional[RepoConfigInput] = None,
        github_client: Optional[GitHubClientInput] = None,
        features_filter: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute feature extraction.

        Args:
            git_history: Git history input (bare repo access)
            git_worktree: Git worktree input (filesystem access)
            repo: Repository metadata from RawRepository
            workflow_run: Workflow run data from RawWorkflowRun
            repo_config: Optional user config (ci_provider, test_frameworks)
            github_client: Optional GitHub client for API features
            features_filter: Optional set of features to extract

        Returns:
            Dictionary of feature_name -> value
        """
        inputs: Dict[str, Any] = {
            "git_history": git_history,
            "git_worktree": git_worktree,
            "repo": repo,
            "workflow_run": workflow_run,
            "db": self.db,
        }

        # Add repo config if provided
        if repo_config:
            inputs["repo_config"] = repo_config

        # Add github client if provided
        if github_client:
            inputs["github_client"] = github_client

        # Determine which features to extract
        if features_filter:
            final_vars = list(features_filter & self._all_features)
        else:
            # Exclude github features if no client provided
            if github_client:
                final_vars = list(self._all_features)
            else:
                final_vars = [
                    f
                    for f in self._all_features
                    if not f.startswith("gh_num_")
                    or f == "gh_num_commits_on_files_touched"
                ]

        if not final_vars:
            logger.warning("No features to extract")
            return {}

        logger.info(f"Extracting {len(final_vars)} features via Hamilton")

        try:
            result = self._driver.execute(final_vars, inputs=inputs)
            return dict(result)
        except Exception as e:
            logger.error(f"Hamilton pipeline failed: {e}")
            raise

    def visualize_dag(self) -> str:
        """Get DAG visualization (returns graphviz DOT format)."""
        try:
            return self._driver.display_all_functions()
        except Exception:
            return "DAG visualization not available"

    def validate(self) -> list:
        """
        Validate the Hamilton DAG for issues.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        try:
            # Check for circular dependencies (Hamilton does this automatically)
            _ = self._driver.list_available_variables()
        except Exception as e:
            errors.append(f"DAG validation error: {e}")
        return errors
