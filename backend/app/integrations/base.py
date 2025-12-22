"""
Base classes for integration tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolType(str, Enum):
    """Available integration tool types."""

    SONARQUBE = "sonarqube"
    TRIVY = "trivy"


class MetricCategory(str, Enum):
    """Categories for grouping metrics."""

    CODE_QUALITY = "code_quality"
    SECURITY = "security"
    RELIABILITY = "reliability"
    MAINTAINABILITY = "maintainability"
    COVERAGE = "coverage"
    DUPLICATION = "duplication"
    COMPLEXITY = "complexity"
    SIZE = "size"
    METADATA = "metadata"


class MetricDataType(str, Enum):
    """Data types for metric values."""

    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    JSON = "json"


@dataclass
class MetricDefinition:
    """Definition of a metric provided by an integration tool."""

    key: str
    display_name: str
    description: str
    category: MetricCategory
    data_type: MetricDataType
    nullable: bool = False
    example_value: Optional[str] = None
    unit: Optional[str] = None


class IntegrationTool(ABC):
    """
    Base class for integration tools.

    Each tool provides:
    - Availability checking
    - Configuration info
    - Metric definitions
    - Scan execution
    """

    @property
    @abstractmethod
    def tool_type(self) -> ToolType:
        """Return the tool type identifier."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of what the tool does."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if tool is configured and ready to use."""
        ...

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Return current configuration (without secrets)."""
        ...

    @abstractmethod
    def get_scan_types(self) -> List[str]:
        """Return list of scan types this tool supports."""
        ...

    @abstractmethod
    def get_metrics(self) -> List[MetricDefinition]:
        """Return list of metrics this tool can provide."""
        ...

    @abstractmethod
    def get_metric_keys(self) -> List[str]:
        """Return list of metric keys (for API responses)."""
        ...

    def to_info_dict(self) -> Dict[str, Any]:
        """Convert tool info to dictionary for API responses."""
        return {
            "type": self.tool_type.value,
            "display_name": self.display_name,
            "description": self.description,
            "is_available": self.is_available(),
            "config": self.get_config(),
            "scan_types": self.get_scan_types(),
            "metric_count": len(self.get_metric_keys()),
        }
