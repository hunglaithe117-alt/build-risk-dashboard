"""
Hamilton-based feature pipeline runner.

This module provides the HamiltonPipeline class that executes
feature extraction using the Hamilton DAG framework.

Key behaviors:
- DEFAULT_FEATURES are always included when features_filter is specified
- Hamilton automatically computes only the dependencies needed for requested features
- Output is filtered to only return the explicitly requested features (+ defaults)
- Caching support for intermediate values to avoid recomputation on errors
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

from hamilton import driver

from app.config import settings

from app.tasks.pipeline.feature_dag import (
    build_features,
    git_features,
    github_features,
    repo_features,
)
from app.tasks.pipeline.feature_dag._inputs import (
    GitHistoryInput,
    GitHubClientInput,
    GitWorktreeInput,
    RepoConfigInput,
    RepoInput,
    BuildRunInput,
    BuildLogsInput,
)
from app.tasks.pipeline.constants import DEFAULT_FEATURES
from app.tasks.pipeline.feature_dag._metadata import (
    get_required_resources_for_features,
    FeatureResource,
)
from app.tasks.pipeline.execution_tracker import ExecutionTracker, ExecutionResult

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
            build_run=BuildRunInput(...),
            features_filter={"tr_status", "gh_num_commits_on_files_touched"},
        )

    Behavior:
        - DEFAULT_FEATURES are always included in the output
        - Hamilton only computes dependencies needed for requested features
        - Output contains only the requested features (+ defaults)
        - Caching stores intermediate values to avoid recomputation
    """

    def __init__(
        self,
        db: Any,
        enable_tracking: bool = True,
        enable_cache: Optional[bool] = None,
    ):
        """
        Initialize the Hamilton pipeline.

        Args:
            db: MongoDB database instance
            enable_tracking: Whether to enable execution tracking (default: True)
            enable_cache: Whether to enable caching (default: from settings)
        """
        self.db = db
        self._enable_tracking = enable_tracking
        self._enable_cache = (
            enable_cache
            if enable_cache is not None
            else settings.HAMILTON_CACHE_ENABLED
        )
        self._tracker: Optional[ExecutionTracker] = None
        self._cache_path: Optional[Path] = None
        self._driver = self._build_driver()
        self._all_features = self._get_all_feature_names()

    def _get_cache_path(self) -> Optional[Path]:
        """
        Get the cache directory path if caching is enabled.

        Returns:
            Path to cache directory if file-based caching enabled, None otherwise.
        """
        if not self._enable_cache:
            return None

        cache_type = settings.HAMILTON_CACHE_TYPE.lower()

        if cache_type == "memory":
            # Return None to signal in-memory cache (handled differently)
            return None
        else:
            # File-based persistent cache (default)
            cache_dir = Path(settings.HAMILTON_CACHE_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir

    def _build_driver(self) -> driver.Driver:
        """Build Hamilton driver with all feature modules and optional caching."""
        builder = driver.Builder().with_modules(
            git_features,
            build_features,
            github_features,
            repo_features,
        )

        # Add caching if enabled
        if self._enable_cache:
            cache_type = settings.HAMILTON_CACHE_TYPE.lower()
            if cache_type == "memory":
                # In-memory cache - use default with_cache() without path
                logger.info("Using in-memory Hamilton cache (non-persistent)")
                builder = builder.with_cache()
            else:
                # File-based persistent cache
                self._cache_path = self._get_cache_path()
                if self._cache_path:
                    logger.info(
                        f"Using file-based Hamilton cache at {self._cache_path}"
                    )
                    builder = builder.with_cache(path=str(self._cache_path))

        # Add execution tracker if enabled
        if self._enable_tracking:
            self._tracker = ExecutionTracker()
            builder = builder.with_adapters(self._tracker)

        return builder.build()

    def _get_all_feature_names(self) -> Set[str]:
        """Get all available feature names."""
        return {v.name for v in self._driver.list_available_variables()}

    def get_active_features(self) -> Set[str]:
        """Get set of all active feature names."""
        return self._all_features.copy()

    def _check_available_resources(
        self,
        git_history: Optional[GitHistoryInput],
        git_worktree: Optional[GitWorktreeInput],
        github_client: Optional[GitHubClientInput],
        build_logs: Optional[BuildLogsInput],
    ) -> Set[str]:
        """
        Check which resources are available.

        Returns:
            Set of available resource names
        """
        available = set()

        # Core resources are always available
        available.add(FeatureResource.BUILD_RUN.value)
        available.add(FeatureResource.REPO.value)
        available.add(FeatureResource.REPO_CONFIG.value)
        available.add(FeatureResource.RAW_BUILD_RUNS.value)  # Query builds available

        # Git history (commit available in bare repo)
        if git_history and git_history.is_commit_available:
            available.add(FeatureResource.GIT_HISTORY.value)

        # Git worktree (filesystem ready)
        if git_worktree and git_worktree.is_ready:
            available.add(FeatureResource.GIT_WORKTREE.value)

        # GitHub API client
        if github_client:
            available.add(FeatureResource.GITHUB_API.value)

        # Build logs
        if build_logs and build_logs.is_available:
            available.add(FeatureResource.BUILD_LOGS.value)

        return available

    def _filter_by_resources(
        self,
        features: Set[str],
        available_resources: Set[str],
    ) -> tuple[Set[str], Set[str]]:
        """
        Filter features based on available resources.

        Returns:
            Tuple of (valid_features, skipped_features)
        """
        valid = set()
        skipped = set()

        for feature in features:
            required = get_required_resources_for_features({feature})
            if required <= available_resources:
                valid.add(feature)
            else:
                missing = required - available_resources
                logger.debug(f"Feature {feature} requires missing resources: {missing}")
                skipped.add(feature)

        return valid, skipped

    def run(
        self,
        git_history: GitHistoryInput,
        git_worktree: GitWorktreeInput,
        repo: RepoInput,
        build_run: BuildRunInput,
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
            build_run: Build run data from RawBuildRun
            repo_config: Optional user config (ci_provider, test_frameworks)
            github_client: Optional GitHub client for API features
            features_filter: Optional set of features to extract

        Returns:
            Dictionary of feature_name -> value (only requested features + defaults)

        Note:
            - DEFAULT_FEATURES are always included in the output
            - Hamilton only computes the features you request (+ their dependencies)
            - Dependencies are computed but NOT included in the output
        """
        # Check which resources are available
        available_resources = self._check_available_resources(
            git_history=git_history,
            git_worktree=git_worktree,
            github_client=github_client,
            build_logs=None,  # TODO: Add build_logs parameter
        )

        # Filter features based on available resources
        if features_filter:
            requested_features = (
                features_filter | DEFAULT_FEATURES
            ) & self._all_features
        else:
            requested_features = self._all_features.copy()

        valid_features, skipped_features = self._filter_by_resources(
            requested_features, available_resources
        )

        if skipped_features:
            logger.warning(
                f"Skipping {len(skipped_features)} features due to missing resources: "
                f"{sorted(skipped_features)[:5]}{'...' if len(skipped_features) > 5 else ''}"
            )

        if not valid_features:
            logger.warning("No features to extract after resource validation")
            return {}

        # Build inputs dict
        inputs: Dict[str, Any] = {
            "git_history": git_history,
            "git_worktree": git_worktree,
            "repo": repo,
            "build_run": build_run,
            "raw_build_runs": self.db.get_collection("raw_build_runs"),
        }

        if repo_config:
            inputs["repo_config"] = repo_config

        if github_client:
            inputs["github_client"] = github_client

        # Convert to list for Hamilton
        final_vars = list(valid_features)

        logger.info(f"Extracting {len(final_vars)} features via Hamilton")
        logger.debug(f"Features: {sorted(final_vars)}")

        try:
            # Hamilton computes ONLY the requested features and their dependencies
            # Dependencies are computed internally but not returned in the result
            result = self._driver.execute(final_vars, inputs=inputs)

            # Filter output to only return explicitly requested features
            # (Hamilton may return intermediate values, so we filter)
            filtered_result = {
                k: v for k, v in dict(result).items() if k in requested_features
            }

            return filtered_result

        except Exception as e:
            logger.error(f"Hamilton pipeline failed: {e}")
            raise

    def get_execution_results(self) -> Optional[ExecutionResult]:
        """
        Get execution tracking results after running the pipeline.

        Returns:
            ExecutionResult with timing and status info, or None if tracking disabled.
        """
        if self._tracker:
            return self._tracker.get_results()
        return None

    def reset_tracker(self) -> None:
        """Reset tracker state for reuse with another execution."""
        if self._tracker:
            self._tracker.reset()

    def clear_cache(self) -> bool:
        """
        Clear the Hamilton cache directory.

        Useful when:
        - Feature extractors have been updated
        - Cache has become stale or corrupted
        - Need to force recomputation of all features

        Returns:
            True if cache was cleared, False if no cache to clear.
        """
        import shutil

        if not self._enable_cache:
            logger.info("Caching is disabled, nothing to clear")
            return False

        cache_type = settings.HAMILTON_CACHE_TYPE.lower()
        if cache_type == "memory":
            logger.info("In-memory cache clears automatically on restart")
            return False

        cache_dir = Path(settings.HAMILTON_CACHE_DIR)
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cleared Hamilton cache at {cache_dir}")
            return True

        return False

    @property
    def is_cache_enabled(self) -> bool:
        """Check if caching is enabled for this pipeline instance."""
        return self._enable_cache

    @property
    def cache_path(self) -> Optional[Path]:
        """Get the cache directory path if using file-based cache."""
        return self._cache_path
