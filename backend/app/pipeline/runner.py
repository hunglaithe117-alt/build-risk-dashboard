"""
Pipeline Integration - Bridge between new DAG pipeline and existing Celery tasks.

This module provides:
1. A high-level function to run the entire feature pipeline
2. Integration with existing Celery task structure
3. Backwards compatibility with current BuildSample saving
"""

import logging
from typing import Any, Dict, List, Optional, Set

from bson import ObjectId
from pymongo.database import Database

from app.pipeline.core.context import ExecutionContext
from app.pipeline.core.executor import PipelineExecutor
from app.pipeline.core.registry import feature_registry
from app.pipeline.resources import ResourceManager, ResourceNames
from app.pipeline.resources.git_repo import GitRepoProvider
from app.pipeline.resources.github_client import GitHubClientProvider
from app.pipeline.resources.log_storage import LogStorageProvider
from app.pipeline.constants import DEFAULT_FEATURES

from app.entities.build_sample import BuildSample
from app.entities.imported_repository import ImportedRepository
from app.entities.workflow_run import WorkflowRunRaw
from app.repositories.build_sample import BuildSampleRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository

logger = logging.getLogger(__name__)


class FeaturePipeline:
    """
    High-level interface for running the feature extraction pipeline.

    Usage:
        pipeline = FeaturePipeline(db)
        result = pipeline.run(build_sample, repo, workflow_run)

        if result["status"] == "completed":
            features = result["features"]
    """

    def __init__(
        self,
        db: Database,
        max_workers: int = 4,
    ):
        """
        Initialize the feature pipeline.

        Args:
            db: MongoDB database instance
            max_workers: Maximum parallel workers for execution
        """
        self.db = db
        self.max_workers = max_workers

        self.executor = PipelineExecutor(
            registry=feature_registry,
            max_workers=max_workers,
            fail_fast=False,
            skip_on_dependency_failure=True,
        )

        # Setup resource manager
        self.resource_manager = ResourceManager()
        self.resource_manager.register(GitRepoProvider())
        self.resource_manager.register(GitHubClientProvider())
        self.resource_manager.register(LogStorageProvider())

    def get_active_features(self) -> Set[str]:
        """Get set of all active feature names from code registry."""
        return feature_registry.get_all_features()

    def get_feature_info(self, feature_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a feature from code registry."""
        return feature_registry.get_feature_metadata(feature_name)

    def resolve_feature_ids(self, feature_ids: List) -> Set[str]:
        """
        Resolve feature ObjectIds to feature names.

        Note: With Option C (code-only registry), this method now looks up
        feature names from dataset templates instead of feature_definitions.

        Args:
            feature_ids: List of ObjectId or string ObjectIds

        Returns:
            Set of feature names
        """
        if not feature_ids:
            return set()
        # Since we no longer use DB definitions, return empty set
        # The caller should pass feature names directly
        logger.warning(
            "resolve_feature_ids called but DB definitions are no longer used. "
            "Pass feature names directly instead of IDs."
        )
        return set()

    def validate_pipeline(self) -> List[str]:
        """
        Validate that code nodes are properly configured.

        Returns list of validation errors (empty if valid).
        """
        return feature_registry.validate()

    def run(
        self,
        build_sample: BuildSample,
        repo: ImportedRepository,
        workflow_run: Optional[WorkflowRunRaw] = None,
        parallel: bool = True,
        features_filter: Optional[Set[str]] = None,
        feature_ids: Optional[List] = None,
    ) -> Dict[str, Any]:
        """
        Run the complete feature pipeline.

        Args:
            build_sample: Target build sample entity
            repo: Repository information
            workflow_run: Workflow run data (optional, will be fetched if not provided)
            parallel: Whether to parallelize level execution
            features_filter: Optional set of specific features to extract. When provided,
                             only nodes needed for these features (and their dependencies)
                             will be executed.

        Returns:
            Dict with status, features, errors, and warnings
        """
        # Create execution context
        context = ExecutionContext(
            build_sample=build_sample,
            repo=repo,
            workflow_run=workflow_run,
            db=self.db,
        )

        # Set workflow_run as a resource for nodes that need it
        # Core features that should always be extracted if possible
        # These match the top-level fields in BuildSample
        # Imported DEFAULT_FEATURES from constants

        # Resolve feature_ids to names if provided
        if feature_ids:
            resolved_names = self.resolve_feature_ids(feature_ids)
            if features_filter:
                features_filter = features_filter | resolved_names
            else:
                features_filter = resolved_names

        # Always include default features in the filter
        # This ensures they are calculated even if not explicitly requested by the user
        if features_filter is not None:
            features_filter = features_filter | DEFAULT_FEATURES
        else:
            # If no filter (run all), we don't strictly need to add them,
            # but if we change logic to "implicit none means none", we would.
            # Current logic: None means ALL. So we are good.
            pass

        # Decide which features and nodes to run
        target_features = self._determine_target_features(features_filter)
        context.requested_features = target_features

        if target_features is not None and len(target_features) == 0:
            warning_msg = "No features requested; skipping pipeline execution"
            logger.warning(warning_msg)
            return {
                "status": "completed",
                "features": {},
                "all_features": {},
                "errors": [],
                "warnings": [warning_msg],
                "results": [],
                "feature_count": 0,
                "ml_feature_count": 0,
            }

        nodes_to_run = self._resolve_nodes_for_features(target_features)
        if not nodes_to_run:
            warning_msg = (
                f"No providers found for requested features: {sorted(target_features)}"
                if target_features
                else "No feature nodes registered for execution"
            )
            logger.warning(warning_msg)
            return {
                "status": "completed",
                "features": {},
                "all_features": {},
                "errors": [],
                "warnings": [warning_msg],
                "results": [],
                "feature_count": 0,
                "ml_feature_count": 0,
            }

        # Initialize only the resources required by the selected nodes
        required_resources = self._collect_required_resources(nodes_to_run)
        available_resources = self.resource_manager.get_registered_names()
        resources_to_init = {
            r
            for r in required_resources
            if r in available_resources and not context.has_resource(r)
        }
        missing_resources = {
            r
            for r in required_resources
            if r not in available_resources and not context.has_resource(r)
        }
        if missing_resources:
            logger.warning(
                "No providers registered for required resources: %s",
                ", ".join(sorted(missing_resources)),
            )

        try:
            self.resource_manager.initialize(context, resources_to_init)

            # Execute pipeline
            context = self.executor.execute(
                context,
                node_names=nodes_to_run,
                parallel=parallel,
            )

            # Filter features based on caller request
            extracted_features = context.get_merged_features()
            if features_filter:
                extracted_features = {
                    k: v for k, v in extracted_features.items() if k in features_filter
                }
            # Note: All features from code registry are active by default

            return {
                "status": context.get_final_status(),
                "features": extracted_features,
                "all_features": context.get_merged_features(),  # Unfiltered
                "errors": context.errors,
                "warnings": context.warnings,
                "results": [
                    {
                        "node": r.node_name,
                        "status": r.status.value,
                        "duration_ms": r.duration_ms,
                        "error": r.error,
                    }
                    for r in context.results
                ],
                "feature_count": len(extracted_features),
            }

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "features": context.get_merged_features(),
                "all_features": context.get_merged_features(),
                "errors": [str(e)],
                "warnings": context.warnings,
                "results": [],
                "feature_count": 0,
            }

        finally:
            # Cleanup resources
            self.resource_manager.cleanup_all(context)

    def _determine_target_features(
        self, features_filter: Optional[Set[str]]
    ) -> Optional[Set[str]]:
        """
        Decide which feature names the caller wants.

        Priority:
        1) Explicit features_filter from caller
        2) None -> run all nodes
        """
        if features_filter is not None:
            return set(features_filter)

        # With code-only registry, run all nodes by default
        return None

    def _resolve_nodes_for_features(
        self, target_features: Optional[Set[str]]
    ) -> Set[str]:
        """
        Convert desired features into the minimal set of nodes (plus dependencies)
        required to produce them.
        """
        registry = self.executor.registry

        if target_features is None:
            return set(registry.get_all().keys())

        nodes_to_run: Set[str] = set()
        visited_features: Set[str] = set()
        visited_nodes: Set[str] = set()

        def add_feature(feature_name: str) -> None:
            if feature_name in visited_features:
                return
            visited_features.add(feature_name)

            provider = registry.get_provider(feature_name)
            if not provider:
                logger.warning("No provider registered for feature '%s'", feature_name)
                return

            add_node(provider)

        def add_node(node_name: str) -> None:
            if node_name in visited_nodes:
                return
            visited_nodes.add(node_name)
            nodes_to_run.add(node_name)

            meta = registry.get(node_name)
            if not meta:
                return

            for required_feature in meta.requires_features:
                add_feature(required_feature)

        for feature in target_features:
            add_feature(feature)

        return nodes_to_run

    def _collect_required_resources(self, node_names: Set[str]) -> Set[str]:
        """Gather resource dependencies for the selected nodes."""
        required: Set[str] = set()
        for node_name in node_names:
            meta = self.executor.registry.get(node_name)
            if meta:
                required.update(meta.requires_resources)
        return required

    def visualize_dag(self) -> str:
        """Get ASCII visualization of the feature DAG."""
        from app.pipeline.core.dag import FeatureDAG

        dag = FeatureDAG(feature_registry)
        dag.build()
        return dag.visualize()


def run_feature_pipeline(
    db: Database,
    build_id: str,
) -> Dict[str, Any]:
    """
    Convenience function to run pipeline for a build ID.

    Fetches all necessary entities and runs the pipeline.
    This can replace the current chord/chain in processing.py.
    """
    build_sample_repo = BuildSampleRepository(db)
    repo_repo = ImportedRepositoryRepository(db)
    workflow_run_repo = WorkflowRunRepository(db)

    # Fetch entities
    build_sample = build_sample_repo.find_by_id(ObjectId(build_id))
    if not build_sample:
        return {"status": "error", "message": "BuildSample not found"}

    repo = repo_repo.find_by_id(str(build_sample.repo_id))
    if not repo:
        return {"status": "error", "message": "Repository not found"}

    workflow_run = workflow_run_repo.find_by_repo_and_run_id(
        str(build_sample.repo_id), build_sample.workflow_run_id
    )
    if not workflow_run:
        return {"status": "error", "message": "WorkflowRun not found"}

    # Run pipeline with requested feature IDs from repo
    pipeline = FeaturePipeline(db)

    # Get feature IDs from repo configuration
    feature_ids = getattr(repo, "requested_feature_ids", None) or []

    result = pipeline.run(
        build_sample,
        repo,
        workflow_run,
        feature_ids=feature_ids if feature_ids else None,
    )

    # Save features to BuildSample
    if result["features"]:
        updates = {}
        updates["features"] = result["features"]
        updates["status"] = result["status"]

        if result["errors"]:
            updates["error_message"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["error_message"] = "Warning: " + "; ".join(result["warnings"])

        # Map default features to top-level fields
        DEFAULT_FIELDS = [
            "tr_build_id",
            "tr_build_number",
            "tr_original_commit",
            "git_trigger_commit",
            "git_branch",
            "tr_jobs",
            "tr_status",
            "tr_duration",
            "tr_log_num_jobs",
            "tr_log_tests_run_sum",
        ]

        for field in DEFAULT_FIELDS:
            if field in result["features"]:
                updates[field] = result["features"][field]

        build_sample_repo.update_one(build_id, updates)

    return result
