"""
Data Sources - Abstract layer for data source configuration and feature extraction.

Data sources represent external systems that provide data for feature extraction:
- Git Repository: Commit info, diff features, file history
- CI Build Logs: Test results, job metadata, workflow info
- SonarQube: Code quality metrics
- Trivy: Container and IaC vulnerability scanning

Each data source:
1. Declares which features it can provide
2. Has configurable settings (e.g., API credentials, options)
3. Can be enabled/disabled per enrichment job
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type

from app.pipeline.core.context import ExecutionContext


class DataSourceType(str, Enum):
    """Types of data sources available."""

    GIT = "git"
    BUILD_LOG = "build_log"
    GITHUB_API = "github_api"
    SONARQUBE = "sonarqube"
    TRIVY = "trivy"


class DataSourceStatus(str, Enum):
    """Status of a data source configuration."""

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    ACTIVE = "active"
    ERROR = "error"


@dataclass
class DataSourceConfig:
    """Configuration for a data source."""

    enabled: bool = True
    credentials: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "credentials": self.credentials,
            "options": self.options,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DataSourceConfig":
        return cls(
            enabled=data.get("enabled", True),
            credentials=data.get("credentials", {}),
            options=data.get("options", {}),
        )


@dataclass
class DataSourceMetadata:
    """Metadata about a data source."""

    source_type: DataSourceType
    display_name: str
    description: str
    icon: str = "database"  # Lucide icon name
    requires_config: bool = False
    config_fields: List[Dict[str, Any]] = field(default_factory=list)
    features_provided: Set[str] = field(default_factory=set)
    resource_dependencies: Set[str] = field(default_factory=set)


class DataSource(ABC):
    """
    Abstract base class for data sources.

    A data source wraps one or more feature nodes and provides
    a unified interface for configuration and activation.
    """

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> DataSourceMetadata:
        """
        Return metadata about this data source.

        This is used by the frontend to display configuration options
        and available features.
        """
        pass

    @classmethod
    @abstractmethod
    def get_feature_names(cls) -> Set[str]:
        """
        Return the names of all features this source can provide.

        These should match feature names in the FeatureRegistry.
        """
        pass

    @classmethod
    def validate_config(cls, config: DataSourceConfig) -> List[str]:
        """
        Validate configuration for this data source.

        Returns a list of validation error messages (empty if valid).
        """
        return []

    @classmethod
    def is_available(cls, context: ExecutionContext) -> bool:
        """
        Check if this data source is available for extraction.

        This may check for required resources, credentials, or other prerequisites.
        """
        return True

    @classmethod
    def get_required_resources(cls) -> Set[str]:
        """
        Return the resource names this data source requires.

        These should match resource names used by ResourceProviders.
        """
        return set()


# Registry for data sources
class DataSourceRegistry:
    """Registry for available data sources."""

    def __init__(self):
        self._sources: Dict[DataSourceType, Type[DataSource]] = {}

    def register(
        self, source_type: DataSourceType, source_class: Type[DataSource]
    ) -> None:
        """Register a data source."""
        self._sources[source_type] = source_class

    def get(self, source_type: DataSourceType) -> Optional[Type[DataSource]]:
        """Get a data source by type."""
        return self._sources.get(source_type)

    def get_all(self) -> Dict[DataSourceType, Type[DataSource]]:
        """Get all registered data sources."""
        return self._sources.copy()

    def get_all_metadata(self) -> List[DataSourceMetadata]:
        """Get metadata for all registered data sources."""
        return [source.get_metadata() for source in self._sources.values()]

    def get_features_by_source(self, source_type: DataSourceType) -> Set[str]:
        """Get all features provided by a data source."""
        source = self._sources.get(source_type)
        if source:
            return source.get_feature_names()
        return set()

    def get_source_for_feature(self, feature_name: str) -> Optional[DataSourceType]:
        """Find which data source provides a given feature."""
        for source_type, source_class in self._sources.items():
            if feature_name in source_class.get_feature_names():
                return source_type
        return None


# Global registry instance
data_source_registry = DataSourceRegistry()


def register_data_source(source_type: DataSourceType):
    """Decorator to register a data source."""

    def decorator(cls: Type[DataSource]) -> Type[DataSource]:
        data_source_registry.register(source_type, cls)
        return cls

    return decorator


__all__ = [
    "DataSource",
    "DataSourceType",
    "DataSourceStatus",
    "DataSourceConfig",
    "DataSourceMetadata",
    "DataSourceRegistry",
    "data_source_registry",
    "register_data_source",
]
