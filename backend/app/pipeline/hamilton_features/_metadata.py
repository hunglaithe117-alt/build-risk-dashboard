"""
Feature metadata decorators for Hamilton DAG.

Replaces the separate feature_metadata files by allowing metadata to be
attached directly to Hamilton feature functions using custom decorators.

Usage:
    @feature_metadata(
        display_name="Build ID",
        description="Unique identifier for the workflow run",
        category="workflow",
        data_type="integer",
    )
    @tag(group="build_log")
    def tr_build_id(workflow_run: WorkflowRunInput) -> int:
        return workflow_run.workflow_run_id
"""

from typing import Any, Callable, Dict, Optional, TypeVar
from enum import Enum

F = TypeVar("F", bound=Callable)


class FeatureCategory(str, Enum):
    """Categories for features."""

    BUILD_LOG = "build_log"
    GIT_HISTORY = "git_history"
    GIT_DIFF = "git_diff"
    REPO_SNAPSHOT = "repo_snapshot"
    PR_INFO = "pr_info"
    DISCUSSION = "discussion"
    TEAM = "team"
    METADATA = "metadata"
    WORKFLOW = "workflow"


class FeatureDataType(str, Enum):
    """Data types for features."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    LIST_STRING = "list_string"
    LIST_INTEGER = "list_integer"
    JSON = "json"


def feature_metadata(
    display_name: str,
    description: str,
    category: str,
    data_type: str,
    nullable: bool = True,
    example_value: Optional[str] = None,
    unit: Optional[str] = None,
) -> Callable[[F], F]:
    """
    Decorator to attach metadata to a Hamilton feature function.

    Args:
        display_name: Human-readable name for UI display
        description: Detailed description of what the feature represents
        category: Feature category (from FeatureCategory enum)
        data_type: Output data type (from FeatureDataType enum)
        nullable: Whether the feature can be None
        example_value: Example output value
        unit: Unit of measurement if applicable

    Returns:
        Decorator function that attaches metadata to the function
    """

    def decorator(func: F) -> F:
        # Store metadata as function attributes
        func.__hamilton_metadata__ = {
            "display_name": display_name,
            "description": description,
            "category": category,
            "data_type": data_type,
            "nullable": nullable,
            "example_value": example_value,
            "unit": unit,
        }
        return func

    return decorator


def get_feature_metadata(func: Callable) -> Optional[Dict[str, Any]]:
    """
    Extract metadata from a feature function.

    Args:
        func: Hamilton feature function

    Returns:
        Dictionary of metadata if present, None otherwise
    """
    return getattr(func, "__hamilton_metadata__", None)


def build_metadata_registry(modules: list) -> Dict[str, Dict[str, Any]]:
    """
    Build a registry of all feature metadata from Hamilton feature modules.

    Args:
        modules: List of Hamilton feature modules to scan

    Returns:
        Dictionary mapping feature names to their metadata
    """
    registry = {}

    for module in modules:
        # Get all functions from module
        for name in dir(module):
            if name.startswith("_"):
                continue

            attr = getattr(module, name)

            # Skip non-callable items
            if not callable(attr):
                continue

            # Check if function has Hamilton metadata
            metadata = get_feature_metadata(attr)
            if metadata:
                registry[name] = metadata

    return registry
