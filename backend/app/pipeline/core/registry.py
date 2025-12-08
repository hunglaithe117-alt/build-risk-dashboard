"""
Feature Registry - Central registry for all feature nodes.

This module provides a decorator-based registration system for feature nodes.
Each feature node declares its dependencies and what features it provides.
"""

from typing import Any, Callable, Dict, List, Optional, Set, Type
from dataclasses import dataclass, field
import logging
from app.pipeline.features import FeatureNode

logger = logging.getLogger(__name__)


@dataclass
class FeatureNodeMeta:
    """Metadata about a registered feature node."""

    name: str
    node_class: Type[FeatureNode]
    requires_features: Set[str] = field(default_factory=set)
    requires_resources: Set[str] = field(default_factory=set)
    provides: Set[str] = field(default_factory=set)
    group: Optional[str] = None
    enabled: bool = True
    priority: int = 0  # Higher priority = executed first when possible


class FeatureRegistry:
    """
    Central registry for feature nodes.

    Usage:
        @register_feature(
            name="git_commit_info",
            requires_features={"workflow_run_data"},
            requires_resources={"git_repo"},
            provides={"git_all_built_commits", "git_prev_built_commit"},
            group="git"
        )
        class GitCommitInfoNode(FeatureNode):
            ...
    """

    def __init__(self):
        self._nodes: Dict[str, FeatureNodeMeta] = {}
        self._feature_providers: Dict[str, str] = {}  # feature_name -> node_name

    def register(
        self,
        name: str,
        node_class: Type["FeatureNode"],
        requires_features: Optional[Set[str]] = None,
        requires_resources: Optional[Set[str]] = None,
        provides: Optional[Set[str]] = None,
        group: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0,
    ) -> None:
        """Register a feature node."""
        if name in self._nodes:
            logger.warning(f"Feature node '{name}' already registered, overwriting")

        meta = FeatureNodeMeta(
            name=name,
            node_class=node_class,
            requires_features=requires_features or set(),
            requires_resources=requires_resources or set(),
            provides=provides or set(),
            group=group,
            enabled=enabled,
            priority=priority,
        )

        self._nodes[name] = meta

        # Track which node provides which features
        for feature in meta.provides:
            if feature in self._feature_providers:
                existing = self._feature_providers[feature]
                logger.warning(
                    f"Feature '{feature}' already provided by '{existing}', "
                    f"now provided by '{name}'"
                )
            self._feature_providers[feature] = name

        logger.debug(f"Registered feature node: {name}")

    def get(self, name: str) -> Optional[FeatureNodeMeta]:
        """Get a feature node by name."""
        return self._nodes.get(name)

    def get_all(self, enabled_only: bool = True) -> Dict[str, FeatureNodeMeta]:
        """Get all registered nodes."""
        if enabled_only:
            return {k: v for k, v in self._nodes.items() if v.enabled}
        return self._nodes.copy()

    def get_by_group(self, group: str) -> Dict[str, FeatureNodeMeta]:
        """Get all nodes in a group."""
        return {k: v for k, v in self._nodes.items() if v.group == group}

    def get_provider(self, feature_name: str) -> Optional[str]:
        """Get the node that provides a feature."""
        return self._feature_providers.get(feature_name)

    def get_all_features(self) -> Set[str]:
        """Get all features that can be extracted."""
        return set(self._feature_providers.keys())

    def validate(self) -> List[str]:
        """
        Validate the registry for issues.
        Returns a list of error messages.
        """
        errors = []

        for name, meta in self._nodes.items():
            # Check required features exist
            for req_feature in meta.requires_features:
                if req_feature not in self._feature_providers:
                    errors.append(
                        f"Node '{name}' requires feature '{req_feature}' "
                        f"which is not provided by any node"
                    )

        return errors

    def clear(self) -> None:
        """Clear all registrations (useful for testing)."""
        self._nodes.clear()
        self._feature_providers.clear()

    def get_dag_version(self) -> str:
        """
        Generate a hash representing the current DAG structure.

        This version hash changes when:
        - Nodes are added/removed
        - Node dependencies change
        - Node provides change

        Useful for tracking which DAG version was used for a pipeline run.
        """
        import hashlib

        nodes = self.get_all(enabled_only=True)
        structure = []

        for name in sorted(nodes.keys()):
            meta = nodes[name]
            node_str = (
                f"{name}:"
                f"provides={sorted(meta.provides)}:"
                f"requires_features={sorted(meta.requires_features)}:"
                f"requires_resources={sorted(meta.requires_resources)}:"
                f"priority={meta.priority}"
            )
            structure.append(node_str)

        full_structure = "\n".join(structure)
        return hashlib.md5(full_structure.encode()).hexdigest()[:8]

    def get_dag_info(self) -> Dict[str, Any]:
        """
        Get comprehensive DAG information for API/monitoring.

        Returns dict with version, node count, feature count, etc.
        """
        nodes = self.get_all(enabled_only=True)
        features = self.get_all_features()

        return {
            "version": self.get_dag_version(),
            "node_count": len(nodes),
            "feature_count": len(features),
            "nodes": list(nodes.keys()),
            "groups": list(set(m.group for m in nodes.values() if m.group)),
        }

    # =========================================================================
    # Metadata Generation (for UI display)
    # =========================================================================

    def _infer_category(self, feature_name: str, group: Optional[str]) -> str:
        """Infer category from feature name and group."""
        if group == "build_log" or feature_name.startswith("tr_"):
            return "build_log"
        if group == "git" and "diff" in feature_name:
            return "git_diff"
        if group == "git":
            return "git_history"
        if group == "repo" or feature_name.startswith("gh_repo"):
            return "repo_snapshot"
        if group == "github" or "comment" in feature_name:
            return "discussion"
        if "team" in feature_name or "core" in feature_name:
            return "team"
        if "pr" in feature_name.lower() or "pull" in feature_name.lower():
            return "pr_info"
        return "metadata"

    def _infer_source(self, resources: Set[str]) -> str:
        """Infer source from required resources."""
        if "log_storage" in resources:
            return "build_log"
        if "git_repo" in resources:
            return "git_repo"
        if "github_client" in resources:
            return "github_api"
        if "workflow_run" in resources:
            return "workflow_run"
        return "metadata"

    def _infer_data_type(self, feature_name: str) -> str:
        """Infer data type from feature name."""
        if (
            feature_name.endswith("_sum")
            or feature_name.endswith("_num")
            or "count" in feature_name
        ):
            return "integer"
        if (
            feature_name.endswith("_rate")
            or "per_kloc" in feature_name
            or "duration" in feature_name
        ):
            return "float"
        if feature_name.endswith("_all") or feature_name.startswith("tr_jobs"):
            return "list_string"
        if "is_" in feature_name or "by_core" in feature_name:
            return "boolean"
        if "at" in feature_name and (
            "started" in feature_name or "created" in feature_name
        ):
            return "datetime"
        return "string"

    def _generate_display_name(self, feature_name: str) -> str:
        """Generate display name from feature name."""
        return (
            feature_name.replace("_", " ").replace("tr ", "").replace("gh ", "").title()
        )

    def get_feature_metadata(self, feature_name: str) -> Optional[Dict]:
        """Get metadata for a single feature."""
        node_name = self._feature_providers.get(feature_name)
        if not node_name:
            return None

        meta = self._nodes.get(node_name)
        if not meta:
            return None

        return {
            "name": feature_name,
            "display_name": self._generate_display_name(feature_name),
            "description": f"Extracted by {node_name}",
            "category": self._infer_category(feature_name, meta.group),
            "source": self._infer_source(meta.requires_resources),
            "data_type": self._infer_data_type(feature_name),
            "extractor_node": node_name,
            "depends_on_features": list(meta.requires_features),
            "depends_on_resources": list(meta.requires_resources),
            "is_active": meta.enabled,
        }

    def get_features_with_metadata(self) -> List[Dict]:
        """Get all features with generated metadata (for API use)."""
        features = []
        for feature_name in self._feature_providers:
            metadata = self.get_feature_metadata(feature_name)
            if metadata:
                features.append(metadata)
        return sorted(features, key=lambda x: (x["category"], x["name"]))

    def get_features_by_node(self) -> Dict[str, List[str]]:
        """Group features by their extractor node."""
        result: Dict[str, List[str]] = {}
        for feature_name, node_name in self._feature_providers.items():
            if node_name not in result:
                result[node_name] = []
            result[node_name].append(feature_name)
        return result

    # =========================================================================
    # Resource Dependency Queries
    # =========================================================================

    def get_features_requiring_resource(self, resource_name: str) -> Set[str]:
        """
        Get all features that require a specific resource.

        Args:
            resource_name: Name of the resource (e.g., "log_storage", "git_repo")

        Returns:
            Set of feature names that require this resource
        """
        features = set()
        for node_name, meta in self._nodes.items():
            if resource_name in meta.requires_resources:
                features.update(meta.provides)
        return features

    def get_nodes_requiring_resource(self, resource_name: str) -> Set[str]:
        """
        Get all node names that require a specific resource.

        Args:
            resource_name: Name of the resource

        Returns:
            Set of node names
        """
        return {
            name
            for name, meta in self._nodes.items()
            if resource_name in meta.requires_resources
        }

    def needs_resource_for_features(
        self, resource_name: str, requested_features: Optional[Set[str]] = None
    ) -> bool:
        """
        Check if any of the requested features require a specific resource.

        Args:
            resource_name: Name of the resource to check
            requested_features: Set of feature names to check.
                               If None, assumes all features are requested.

        Returns:
            True if the resource is needed, False otherwise

        Example:
            # Check if logs are needed for the requested features
            needs_logs = registry.needs_resource_for_features(
                "log_storage",
                {"tr_log_tests_run_sum", "gh_diff_files_added"}
            )
        """
        if requested_features is None:
            # No filter = all features = check if any node needs this resource
            return any(
                resource_name in meta.requires_resources
                for meta in self._nodes.values()
            )

        # Get features that require this resource
        features_needing_resource = self.get_features_requiring_resource(resource_name)

        # Check if any requested feature needs this resource
        return bool(requested_features & features_needing_resource)

    def get_required_resources_for_features(
        self, requested_features: Optional[Set[str]] = None
    ) -> Set[str]:
        """
        Get all resources required to extract the requested features.

        Args:
            requested_features: Set of feature names. If None, returns all resources.

        Returns:
            Set of resource names needed
        """
        if requested_features is None:
            # All resources
            resources = set()
            for meta in self._nodes.values():
                resources.update(meta.requires_resources)
            return resources

        # Find which nodes provide these features
        required_resources = set()
        for feature_name in requested_features:
            node_name = self._feature_providers.get(feature_name)
            if node_name:
                meta = self._nodes.get(node_name)
                if meta:
                    required_resources.update(meta.requires_resources)

        return required_resources


# Global registry instance
feature_registry = FeatureRegistry()


def register_feature(
    name: str,
    requires_features: Optional[Set[str]] = None,
    requires_resources: Optional[Set[str]] = None,
    provides: Optional[Set[str]] = None,
    group: Optional[str] = None,
    enabled: bool = True,
    priority: int = 0,
) -> Callable[[Type["FeatureNode"]], Type["FeatureNode"]]:
    """
    Decorator to register a feature node.

    Example:
        @register_feature(
            name="build_log_features",
            requires_resources={"log_storage", "workflow_run"},
            provides={"tr_log_num_jobs", "tr_log_tests_run_sum", ...},
            group="build_log"
        )
        class BuildLogFeaturesNode(FeatureNode):
            async def extract(self, context: ExecutionContext) -> Dict[str, Any]:
                ...
    """

    def decorator(cls: Type["FeatureNode"]) -> Type["FeatureNode"]:
        feature_registry.register(
            name=name,
            node_class=cls,
            requires_features=requires_features,
            requires_resources=requires_resources,
            provides=provides,
            group=group,
            enabled=enabled,
            priority=priority,
        )
        # Store metadata on class for introspection
        cls._feature_meta = {
            "name": name,
            "requires_features": requires_features or set(),
            "requires_resources": requires_resources or set(),
            "provides": provides or set(),
            "group": group,
        }
        return cls

    return decorator
