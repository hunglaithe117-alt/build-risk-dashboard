"""
Resource Providers - Base class and interfaces for pipeline resources.

Resources are shared dependencies that feature nodes need:
- Git repository (cloned, with commit ensured)
- GitHub API client
- Build log storage
- Workflow run data
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from app.pipeline.core.context import ExecutionContext


class ResourceProvider(ABC):
    """
    Base class for resource providers.
    
    Resource providers are responsible for:
    1. Initializing expensive resources (git clone, API clients)
    2. Making them available in the execution context
    3. Cleaning up after pipeline execution
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this resource."""
        pass
    
    @abstractmethod
    def initialize(self, context: "ExecutionContext") -> Any:
        """
        Initialize the resource and return it.
        
        The returned value will be stored in context.resources[self.name]
        """
        pass
    
    def cleanup(self, context: "ExecutionContext") -> None:
        """
        Clean up the resource after pipeline execution.
        
        Override this to release resources like file handles, connections, etc.
        """
        pass
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"


class ResourceManager:
    """
    Manages initialization and cleanup of all resources.
    """
    
    def __init__(self):
        self._providers: Dict[str, ResourceProvider] = {}
    
    def register(self, provider: ResourceProvider) -> None:
        """Register a resource provider."""
        self._providers[provider.name] = provider
    
    def initialize_all(self, context: "ExecutionContext") -> None:
        """Initialize all registered resources."""
        for name, provider in self._providers.items():
            try:
                resource = provider.initialize(context)
                context.set_resource(name, resource)
            except Exception as e:
                raise ResourceInitializationError(
                    f"Failed to initialize resource '{name}': {e}"
                ) from e
    
    def cleanup_all(self, context: "ExecutionContext") -> None:
        """Cleanup all resources."""
        for name, provider in self._providers.items():
            try:
                provider.cleanup(context)
            except Exception as e:
                # Log but don't raise - we want to cleanup all resources
                import logging
                logging.getLogger(__name__).error(
                    f"Error cleaning up resource '{name}': {e}"
                )


class ResourceInitializationError(Exception):
    """Raised when a resource fails to initialize."""
    pass


# Pre-defined resource names for type safety
class ResourceNames:
    """Standard resource names used across the pipeline."""
    GIT_REPO = "git_repo"
    GITHUB_CLIENT = "github_client"
    LOG_STORAGE = "log_storage"
    WORKFLOW_RUN = "workflow_run"
    BUILD_SAMPLE_REPO = "build_sample_repo"
