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

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set

from hamilton import driver

from app.config import settings
from app.paths import HAMILTON_CACHE_DIR
from app.tasks.pipeline.constants import DEFAULT_FEATURES
from app.tasks.pipeline.execution_tracker import ExecutionResult, ExecutionTracker
from app.tasks.pipeline.feature_dag import (
    build_features,
    devops_features,
    git_features,
    github_features,
    history_features,
    log_features,
    repo_features,
)
from app.tasks.pipeline.feature_dag._inputs import (
    BuildLogsInput,
    BuildRunInput,
    FeatureConfigInput,
    GitHistoryInput,
    GitHubClientInput,
    GitWorktreeInput,
    RepoInput,
)
from app.tasks.pipeline.feature_dag._metadata import get_required_resources_for_features
from app.tasks.pipeline.input_preparer import PreparedPipelineInput
from app.tasks.pipeline.shared.resources import (
    check_resource_availability,
    get_input_resource_names,
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
            enable_cache if enable_cache is not None else settings.HAMILTON_CACHE_ENABLED
        )
        self._tracker: Optional[ExecutionTracker] = None
        self._cache_path: Optional[Path] = None
        self._driver = self._build_driver()
        self._all_features = self._get_all_feature_names()
        # Track skipped features and missing resources after run()
        self._last_skipped_features: Set[str] = set()
        self._last_missing_resources: Set[str] = set()

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
            cache_dir = Path(HAMILTON_CACHE_DIR)
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir

    def _build_driver(self) -> driver.Driver:
        """Build Hamilton driver with all feature modules and optional caching."""
        builder = driver.Builder().with_modules(
            git_features,
            build_features,
            github_features,
            log_features,
            repo_features,
            history_features,
            devops_features,
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
                    logger.info(f"Using file-based Hamilton cache at {self._cache_path}")
                    builder = builder.with_cache(path=str(self._cache_path))

        # Add execution tracker if enabled
        if self._enable_tracking:
            self._tracker = ExecutionTracker()
            builder = builder.with_adapters(self._tracker)

        return builder.build()

    def _get_all_feature_names(self) -> Set[str]:
        """Get all actual feature output names (excludes inputs and intermediate nodes).

        Uses build_metadata_registry() to get only features with @feature_metadata decorator,
        which are the actual output features defined in the feature DAG modules.
        """
        from app.tasks.pipeline.feature_dag._metadata import build_metadata_registry

        registry = build_metadata_registry(
            [
                git_features,
                build_features,
                github_features,
                log_features,
                repo_features,
                history_features,
                devops_features,
            ]
        )
        return set(registry.keys())

    def get_active_features(self) -> Set[str]:
        """Get set of all active feature names."""
        return self._all_features.copy()

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

    def execute(
        self,
        prepared: PreparedPipelineInput,
    ) -> Dict[str, Any]:
        """
        Execute Hamilton pipeline with prepared inputs.

        This is the pure executor - all input preparation and resource
        checking is done by prepare_pipeline_input().

        Args:
            prepared: PreparedPipelineInput from input_preparer

        Returns:
            Dictionary of feature_name -> value
        """

        # Store tracking info from prepared input
        self._last_skipped_features = prepared.skipped_features
        self._last_missing_resources = prepared.missing_resources

        if not prepared.has_features:
            logger.warning("No features to extract")
            return {}

        # Build Hamilton inputs dict
        inputs: Dict[str, Any] = {
            "git_history": prepared.inputs.git_history,
            "git_worktree": prepared.inputs.git_worktree,
            "repo": prepared.inputs.repo,
            "build_run": prepared.inputs.build_run,
            "feature_config": prepared.inputs.feature_config,
            "build_logs": prepared.inputs.build_logs,
            "raw_build_runs": self.db.get_collection("raw_build_runs"),
            "model_training_builds": self.db.get_collection("model_training_builds"),
        }

        if prepared.github_client:
            inputs["github_client"] = prepared.github_client

        final_vars = list(prepared.features_to_extract)
        logger.info(f"Extracting {len(final_vars)} features via Hamilton")
        logger.debug(f"Features: {sorted(final_vars)}")

        try:
            result = self._driver.execute(final_vars, inputs=inputs)

            # Filter output to only return requested features
            input_names = get_input_resource_names()
            filtered_result = {
                k: v
                for k, v in dict(result).items()
                if k in prepared.features_to_extract and k not in input_names
            }

            return filtered_result

        except Exception as e:
            logger.error(f"Hamilton pipeline failed: {e}")
            raise

    def run(
        self,
        git_history: GitHistoryInput,
        git_worktree: GitWorktreeInput,
        repo: RepoInput,
        build_run: BuildRunInput,
        feature_config: Optional[FeatureConfigInput] = None,
        github_client: Optional[GitHubClientInput] = None,
        build_logs: Optional[BuildLogsInput] = None,
        features_filter: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute feature extraction (legacy interface).

        For new code, prefer using prepare_pipeline_input() + execute().

        This method builds inputs dict, checks resources, and executes.
        """
        # Build inputs dict
        inputs: Dict[str, Any] = {
            "git_history": git_history,
            "git_worktree": git_worktree,
            "repo": repo,
            "build_run": build_run,
            "raw_build_runs": self.db.get_collection("raw_build_runs"),
            "model_training_builds": self.db.get_collection("model_training_builds"),
        }

        if feature_config:
            inputs["feature_config"] = feature_config

        if github_client:
            inputs["github_client"] = github_client

        if build_logs:
            inputs["build_logs"] = build_logs

        # Check resources and filter features
        available_resources = check_resource_availability(inputs)

        if features_filter:
            requested_features = (features_filter | DEFAULT_FEATURES) & self._all_features
        else:
            requested_features = self._all_features.copy()

        valid_features, skipped_features = self._filter_by_resources(
            requested_features, available_resources
        )

        all_required = get_required_resources_for_features(requested_features)
        missing_resources = all_required - available_resources

        self._last_skipped_features = skipped_features
        self._last_missing_resources = missing_resources

        if skipped_features:
            logger.warning(
                f"Skipping {len(skipped_features)} features due to missing resources: "
                f"{sorted(skipped_features)[:5]}{'...' if len(skipped_features) > 5 else ''}"
            )
            logger.warning(f"Missing resources: {sorted(missing_resources)}")

        if not valid_features:
            logger.warning("No features to extract after resource validation")
            return {}

        input_names = get_input_resource_names()
        final_vars = list(valid_features - input_names)

        logger.info(f"Extracting {len(final_vars)} features via Hamilton")
        logger.debug(f"Features: {sorted(final_vars)}")

        try:
            result = self._driver.execute(final_vars, inputs=inputs)

            filtered_result = {
                k: v
                for k, v in dict(result).items()
                if k in requested_features and k not in input_names
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

        cache_dir = Path(HAMILTON_CACHE_DIR)
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

    @property
    def skipped_features(self) -> Set[str]:
        """Get features skipped in last run due to missing resources."""
        return self._last_skipped_features.copy()

    @property
    def missing_resources(self) -> Set[str]:
        """Get resources that were missing in last run."""
        return self._last_missing_resources.copy()
