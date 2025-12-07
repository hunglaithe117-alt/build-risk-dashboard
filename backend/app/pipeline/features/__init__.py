"""
Feature Node Base Class.

All feature extractors inherit from this class and implement the extract method.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from app.pipeline.core.context import ExecutionContext


class FeatureNode(ABC):
    """
    Base class for feature extraction nodes.

    Each node:
    - Declares its dependencies (requires_features, requires_resources)
    - Declares what features it provides
    - Implements extract() to compute features

    Example:
        @register_feature(
            name="git_commit_info",
            requires_resources={"git_repo"},
            provides={"git_all_built_commits", "git_prev_built_commit", "git_prev_commit_resolution_status"},
            group="git"
        )
        class GitCommitInfoNode(FeatureNode):
            def extract(self, context: ExecutionContext) -> Dict[str, Any]:
                git_handle = context.get_resource("git_repo")
                # ... extraction logic
                return {
                    "git_all_built_commits": [...],
                    "git_prev_built_commit": "abc123",
                    "git_prev_commit_resolution_status": "found",
                }
    """

    @abstractmethod
    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        """
        Extract features and return them as a dictionary.

        Args:
            context: Execution context with resources and previously extracted features

        Returns:
            Dictionary of feature_name -> value

        Raises:
            Exception: If extraction fails (will be caught and recorded)
        """
        pass

    def validate_output(self, features: Dict[str, Any]) -> None:
        """
        Optional validation of extracted features.

        Override to add custom validation logic.
        Raises ValueError if validation fails.
        """
        pass

    @classmethod
    def get_empty_features(cls) -> Dict[str, Any]:
        """
        Return empty/default values for all features this node provides.

        Useful for partial failures or when source data is missing.
        """
        return {}
