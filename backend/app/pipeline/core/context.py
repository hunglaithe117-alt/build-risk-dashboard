"""Execution context for feature pipeline."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExecutionContext:
    """Minimal execution context for backward compatibility with Hamilton."""

    resources: Dict[str, Any] = field(default_factory=dict)
    repo_id: Optional[str] = None
    workflow_run_id: Optional[str] = None

    def get_resource(self, name: str) -> Any:
        """Get a resource by name."""
        return self.resources.get(name)

    def set_resource(self, name: str, resource: Any) -> None:
        """Set a resource."""
        self.resources[name] = resource


@dataclass
class FeatureResult:
    """Result container for feature extraction (not used with Hamilton)."""

    feature_name: str
    value: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
