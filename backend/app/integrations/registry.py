"""
Tool registry for managing integration tools.
"""

from typing import Dict, List, Optional
from .base import IntegrationTool, ToolType


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


def _register_default_tools() -> None:
    """Register the default tools (SonarQube, Trivy)."""
    from .tools.sonarqube import SonarQubeTool
    from .tools.trivy import TrivyTool

    tool_registry.register(SonarQubeTool())
    tool_registry.register(TrivyTool())


# Auto-register default tools on import
_register_default_tools()
