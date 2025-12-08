"""
Execution Context - Container for pipeline state during feature extraction.

The context flows through all feature nodes and accumulates:
- Resources: Initialized providers (git repo, github client, etc.)
- Features: Extracted feature values (grows as DAG executes)
- Errors: Any errors encountered during extraction
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from app.entities.build_sample import BuildSample
    from app.entities.imported_repository import ImportedRepository
    from app.entities.workflow_run import WorkflowRunRaw


class FeatureStatus(str, Enum):
    """Status of a feature extraction."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FeatureResult:
    """Result of a single feature node extraction."""

    node_name: str
    status: FeatureStatus
    features: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    warning: Optional[str] = None
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == FeatureStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status == FeatureStatus.FAILED


@dataclass
class ExecutionContext:
    """
    Runtime context for pipeline execution.

    This context is passed to every feature node and contains:
    - Entity references (build_sample, repo, workflow_run)
    - Initialized resources (git repo handle, github client, etc.)
    - Accumulated features from previously executed nodes
    - Tracking of execution results
    """

    # Core entities
    build_sample: "BuildSample"
    repo: "ImportedRepository"
    workflow_run: Optional["WorkflowRunRaw"] = None

    # Database reference (for accessing repositories if needed)
    db: Any = None

    # Initialized resources (populated by ResourceProviders)
    # Keys: resource names like "git_repo", "github_client"
    resources: Dict[str, Any] = field(default_factory=dict)

    # Accumulated features from all executed nodes
    # This grows as the DAG executes
    features: Dict[str, Any] = field(default_factory=dict)

    # Results from each feature node
    results: List[FeatureResult] = field(default_factory=list)

    # Global errors/warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Feature selection (optional)
    requested_features: Optional[Set[str]] = None

    # Lazy resource tracking
    _lazy_resources: Dict[str, Any] = field(default_factory=dict)
    _lazy_providers: Dict[str, Any] = field(default_factory=dict)

    def get_resource(self, name: str) -> Any:
        """
        Get a resource by name, initializing lazily if needed.

        Raises KeyError if resource is not found and cannot be initialized.
        """
        # Check if already initialized
        if name in self.resources:
            return self.resources[name]

        # Check for lazy resource
        if name in self._lazy_resources:
            lazy = self._lazy_resources[name]
            try:
                value = lazy.value  # Triggers initialization
                self.resources[name] = value  # Cache for future calls
                return value
            except Exception as e:
                raise KeyError(
                    f"Failed to lazy-initialize resource '{name}': {e}"
                ) from e

        raise KeyError(
            f"Resource '{name}' not found in context. "
            f"Available: {list(self.resources.keys())}"
        )

    def has_resource(self, name: str) -> bool:
        """Check if a resource exists (eager or lazy)."""
        return name in self.resources or name in self._lazy_resources

    def set_resource(self, name: str, value: Any) -> None:
        """Set a resource value (eager mode)."""
        self.resources[name] = value

    def set_lazy_resource(
        self, name: str, lazy_wrapper: Any, provider: Any = None
    ) -> None:
        """
        Register a lazy resource.

        Args:
            name: Resource name
            lazy_wrapper: LazyResource wrapper
            provider: Optional provider for cleanup
        """
        self._lazy_resources[name] = lazy_wrapper
        if provider:
            self._lazy_providers[name] = provider

    def get_feature(self, name: str, default: Any = None) -> Any:
        """Get a feature value by name."""
        return self.features.get(name, default)

    def has_feature(self, name: str) -> bool:
        """Check if a feature has been extracted."""
        return name in self.features

    def get_features(self, *names: str) -> Dict[str, Any]:
        """Get multiple features as a dict."""
        return {name: self.features.get(name) for name in names}

    def merge_features(self, features: Dict[str, Any]) -> None:
        """Merge extracted features into context."""
        self.features.update(features)

    def add_result(self, result: FeatureResult) -> None:
        """Add a feature node result."""
        self.results.append(result)
        if result.is_success:
            self.merge_features(result.features)
        if result.error:
            self.errors.append(f"[{result.node_name}] {result.error}")
        if result.warning:
            self.warnings.append(f"[{result.node_name}] {result.warning}")

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)

    def get_final_status(self) -> str:
        """Determine final status based on all results."""
        if any(r.is_failed for r in self.results):
            return "failed"
        return "completed"

    def get_merged_features(self) -> Dict[str, Any]:
        """Get all merged features."""
        return self.features.copy()

    def get_error_message(self) -> Optional[str]:
        """Get combined error message if any errors occurred."""
        if not self.errors:
            return None
        return "; ".join(self.errors)

    def get_warning_message(self) -> Optional[str]:
        """Get combined warning message."""
        if not self.warnings:
            return None
        return "; ".join(self.warnings)

    def is_feature_requested(self, feature_name: str) -> bool:
        """
        Check whether a feature is part of the requested set.
        None means all features are requested (default).
        """
        return (
            True
            if self.requested_features is None
            else feature_name in self.requested_features
        )
