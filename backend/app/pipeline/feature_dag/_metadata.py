"""
Feature metadata decorators for Hamilton DAG.

Replaces the separate feature_metadata files by allowing metadata to be
attached directly to Hamilton feature functions using custom decorators.

Usage:
    @feature_metadata(
        display_name="Build ID",
        description="Unique identifier for the workflow run",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_RUN],
    )
    @tag(group="build_log")
    def tr_build_id(build_run: BuildRunInput) -> int:
        return int(build_run.build_id)
"""

from typing import Any, Callable, Dict, List, Optional, Set, TypeVar
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


class FeatureResource(str, Enum):
    """
    Resources required by features.

    Resources form a DAG with dependencies.
    Use RESOURCE_DAG to define the full dependency graph.
    """

    # Core inputs (always available from DB, no ingestion needed)
    BUILD_RUN = "build_run"  # Single RawBuildRun entity (current build)
    REPO = "repo"  # RawRepository metadata
    REPO_CONFIG = "repo_config"  # User-configured repo settings

    # Collection access (for querying other builds)
    RAW_BUILD_RUNS = "raw_build_runs"  # Query raw_build_runs collection

    # Git resources (require ingestion)
    GIT_HISTORY = "git_history"  # Git bare repo (clone_repo task)
    GIT_WORKTREE = "git_worktree"  # Git worktree (create_worktrees_batch task)

    # External resources
    GITHUB_API = "github_api"  # GitHub API client (on-demand, no ingestion)
    BUILD_LOGS = "build_logs"  # CI job logs (download_build_logs task)


# Note: Resource DAG is now defined in app.pipeline.resource_dag using Hamilton
# See resource_dag.py for the full DAG with dependencies


def get_ingestion_tasks_for_resources(required_resources: Set[str]) -> List[str]:
    """
    Get ordered list of ingestion tasks for required resources.

    Delegates to Hamilton-based resource_dag for automatic dependency resolution.
    """
    from app.pipeline.resource_dag import get_ingestion_tasks

    return get_ingestion_tasks(list(required_resources))


class OutputFormat(str, Enum):
    """Output format for list features when saving to DB."""

    RAW = "raw"
    COMMA_SEPARATED = "comma"  # "a,b,c"
    HASH_SEPARATED = "hash"  # "a#b#c"
    PIPE_SEPARATED = "pipe"  # "a|b|c"


def feature_metadata(
    display_name: str,
    description: str,
    category: FeatureCategory,
    data_type: FeatureDataType,
    required_resources: Optional[List[FeatureResource]] = None,
    nullable: bool = True,
    example_value: Optional[str] = None,
    unit: Optional[str] = None,
    output_format: Optional[OutputFormat] = None,
    output_formats: Optional[Dict[str, OutputFormat]] = None,
) -> Callable[[F], F]:
    """
    Decorator to attach metadata to a Hamilton feature function.

    Args:
        display_name: Human-readable name for UI display
        description: Detailed description of what the feature represents
        category: Feature category (from FeatureCategory enum)
        data_type: Output data type (from FeatureDataType enum)
        required_resources: List of resources needed to compute this feature
        nullable: Whether the feature can be None
        example_value: Example output value
        unit: Unit of measurement if applicable
        output_format: How to format list values for storage (for single-value features)
        output_formats: Dict mapping field names to formats (for @extract_fields features)
                       Example: {"git_all_built_commits": OutputFormat.HASH_SEPARATED}

    Returns:
        Decorator function that attaches metadata to the function
    """

    def decorator(func: F) -> F:
        # Convert output_formats dict values to strings
        formats_dict = {}
        if output_formats:
            for k, v in output_formats.items():
                formats_dict[k] = v.value if isinstance(v, Enum) else v

        # Store metadata as function attributes
        func.__hamilton_metadata__ = {
            "display_name": display_name,
            "description": description,
            "category": category.value if isinstance(category, Enum) else category,
            "data_type": data_type.value if isinstance(data_type, Enum) else data_type,
            "required_resources": [
                r.value if isinstance(r, Enum) else r
                for r in (required_resources or [])
            ],
            "nullable": nullable,
            "example_value": example_value,
            "unit": unit,
            "output_format": (
                output_format.value
                if isinstance(output_format, Enum)
                else output_format
            ),
            "output_formats": formats_dict,
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

    Also registers extracted field names (from @extract_fields) with their
    parent function's metadata so resource detection works for individual fields.

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

                # Also check for @extract_fields decorator
                # Hamilton stores extract_fields info in func.transform attribute
                transforms = getattr(attr, "transform", [])
                for t in transforms:
                    # Check if this is an extract_fields transform
                    if hasattr(t, "fields") and isinstance(t.fields, dict):
                        for field_name in t.fields.keys():
                            # Register extracted field name with same metadata
                            registry[field_name] = metadata

    return registry


def get_required_resources_for_features(
    feature_names: Set[str],
    modules: Optional[list] = None,
) -> Set[str]:
    """
    Get all required resources for a set of features.

    This is useful for optimizing resource loading - only prepare resources
    that are actually needed by the requested features.

    Args:
        feature_names: Set of feature names to check
        modules: Optional list of Hamilton modules. If not provided,
                 lazy-loads HAMILTON_MODULES from constants to avoid
                 circular imports.

    Returns:
        Set of resource names required (e.g., {"git_history", "github_api"})
    """
    # Lazy load to avoid circular import
    if modules is None:
        from app.pipeline.constants import HAMILTON_MODULES

        modules = HAMILTON_MODULES

    registry = build_metadata_registry(modules)
    resources: Set[str] = set()

    # Include default features that are always extracted
    # Lazy load DEFAULT_FEATURES to avoid circular import
    from app.pipeline.constants import DEFAULT_FEATURES

    features = feature_names | DEFAULT_FEATURES

    for name in features:
        if name in registry:
            feature_resources = registry[name].get("required_resources", [])
            resources.update(feature_resources)

    return resources


def format_features_for_storage(
    features: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Format feature values.

    Args:
        features: Dictionary of extracted features
    Returns:
        Dictionary with formatted values ready for DB storage
    """
    # Lazy load to avoid circular import
    from app.pipeline.constants import HAMILTON_MODULES

    registry = build_metadata_registry(HAMILTON_MODULES)
    result = {}

    for name, value in features.items():
        # Get output format from metadata
        metadata = registry.get(name, {})

        # First check output_formats dict (for @extract_fields features)
        output_formats_dict = metadata.get("output_formats", {})
        output_format_str = output_formats_dict.get(name)

        # Fall back to output_format (for single-value features)
        if not output_format_str:
            output_format_str = metadata.get("output_format")

        # Convert string to enum if needed
        if output_format_str:
            try:
                output_format = OutputFormat(output_format_str)
            except ValueError:
                output_format = OutputFormat.RAW
        else:
            output_format = OutputFormat.RAW

        if value is None:
            result[name] = None
        elif isinstance(value, list):
            if not value:
                result[name] = ""
            elif output_format == OutputFormat.HASH_SEPARATED:
                result[name] = "#".join(str(v) for v in value)
            elif output_format == OutputFormat.COMMA_SEPARATED:
                result[name] = ",".join(str(v) for v in value)
            elif output_format == OutputFormat.PIPE_SEPARATED:
                result[name] = "|".join(str(v) for v in value)
            else:
                # RAW - keep as list
                result[name] = value
        else:
            result[name] = value

    return result
