"""
Tool registry for managing integration tools.
"""

from typing import Any, Dict, List, Optional

from .base import IntegrationTool


class ToolRegistry:
    """Registry for integration tools."""

    def __init__(self):
        self._tools: Dict[str, IntegrationTool] = {}

    def register(self, tool: IntegrationTool) -> None:
        """Register a tool in the registry."""
        self._tools[tool.tool_type.value] = tool

    def get(self, tool_type: str) -> Optional[IntegrationTool]:
        """Get a tool by type."""
        return self._tools.get(tool_type)

    def get_all(self) -> List[IntegrationTool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def get_available(self) -> List[IntegrationTool]:
        """Get only available (configured) tools."""
        return [t for t in self._tools.values() if t.is_available()]


# Global registry instance
tool_registry = ToolRegistry()


def get_tool(tool_type: str) -> Optional[IntegrationTool]:
    """Get a tool by type from the global registry."""
    return tool_registry.get(tool_type)


def get_available_tools() -> List[IntegrationTool]:
    """Get all available tools from the global registry."""
    return tool_registry.get_available()


def get_all_tools() -> List[IntegrationTool]:
    """Get all registered tools (regardless of availability)."""
    return tool_registry.get_all()


def get_all_metrics_grouped() -> Dict[str, Dict[str, Any]]:
    """
    Get all metrics from all registered tools, grouped by tool and category.

    Returns:
        Dict with tool_type as key, containing:
        - metrics: Dict grouped by category
        - all_keys: List of all metric keys
        - tool_info: Basic tool info (display_name, description, etc.)
    """
    result = {}

    for tool in tool_registry.get_all():
        tool_type = tool.tool_type.value
        metrics = tool.get_metrics()

        # Group metrics by category
        grouped_metrics: Dict[str, List[Dict[str, Any]]] = {}
        for metric in metrics:
            category = metric.category.value
            if category not in grouped_metrics:
                grouped_metrics[category] = []
            grouped_metrics[category].append(
                {
                    "key": metric.key,
                    "display_name": metric.display_name,
                    "description": metric.description,
                    "data_type": metric.data_type.value,
                    "unit": metric.unit,
                    "example_value": metric.example_value,
                }
            )

        result[tool_type] = {
            "metrics": grouped_metrics,
            "all_keys": [m.key for m in metrics],
            "tool_info": {
                "display_name": tool.display_name,
                "description": tool.description,
                "is_available": tool.is_available(),
                "scan_types": tool.get_scan_types(),
            },
        }

    return result


def _register_default_tools() -> None:
    """Register the default tools (SonarQube, Trivy)."""
    from .tools.sonarqube import SonarQubeTool
    from .tools.trivy import TrivyTool

    tool_registry.register(SonarQubeTool())
    tool_registry.register(TrivyTool())


# Auto-register default tools on import
_register_default_tools()
