"""
Feature Registry - Central registry for all feature nodes.

This module provides a decorator-based registration system for feature nodes.
Each feature node declares its dependencies and what features it provides.
"""

from typing import Callable, Dict, List, Optional, Set, Type, TYPE_CHECKING
from dataclasses import dataclass, field
import logging

if TYPE_CHECKING:
    from app.pipeline.features.base import FeatureNode

logger = logging.getLogger(__name__)


@dataclass
class FeatureNodeMeta:
    """Metadata about a registered feature node."""
    name: str
    node_class: Type["FeatureNode"]
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
