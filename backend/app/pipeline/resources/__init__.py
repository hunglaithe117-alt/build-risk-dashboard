"""
Resource Providers - Base class and interfaces for pipeline resources.

Resources are shared dependencies that feature nodes need:
- Git repository (cloned, with commit ensured)
- GitHub API client
- Build log storage
- Workflow run data

Supports LAZY LOADING: Resources are only initialized when first accessed.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Set, TYPE_CHECKING
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


@dataclass
class LazyResource:
    """
    Wrapper for lazy-initialized resources.

    The resource is only initialized when `.value` is first accessed.
    """

    _provider_fn: Callable[[], Any]
    _value: Any = None
    _initialized: bool = False
    _error: Optional[Exception] = None

    @property
    def value(self) -> Any:
        """Get the resource value, initializing if needed."""
        if not self._initialized:
            try:
                self._value = self._provider_fn()
                self._initialized = True
            except Exception as e:
                self._error = e
                raise ResourceInitializationError(
                    f"Lazy initialization failed: {e}"
                ) from e
        return self._value

    @property
    def is_initialized(self) -> bool:
        return self._initialized


class ResourceManager:
    """
    Manages initialization and cleanup of all resources.

    Supports both eager and lazy initialization:
    - Eager: Resources initialized upfront via `initialize()`
    - Lazy: Resources initialized on first access via `register_lazy()`
    """

    def __init__(self):
        self._providers: Dict[str, ResourceProvider] = {}
        self._logger = logging.getLogger(__name__)

    def register(self, provider: ResourceProvider) -> None:
        """Register a resource provider."""
        self._providers[provider.name] = provider

    def get_registered_names(self) -> Set[str]:
        """Return names of all registered providers."""
        return set(self._providers.keys())

    def get_provider(self, name: str) -> Optional[ResourceProvider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def initialize(
        self,
        context: "ExecutionContext",
        required_resources: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialize only the resources that are required (EAGER mode).

        Args:
            context: Execution context to attach resources to
            required_resources: Optional subset to initialize (defaults to all)
        """
        resource_names = (
            self.get_registered_names()
            if required_resources is None
            else required_resources
        )
        missing = [r for r in resource_names if r not in self._providers]

        if missing:
            self._logger.warning(
                "No provider registered for resources: %s", ", ".join(sorted(missing))
            )

        for name in resource_names:
            provider = self._providers.get(name)
            if not provider:
                continue

            # Skip if resource already exists on context
            if hasattr(context, "has_resource") and context.has_resource(name):
                continue

            try:
                resource = provider.initialize(context)
                context.set_resource(name, resource)
            except Exception as e:
                raise ResourceInitializationError(
                    f"Failed to initialize resource '{name}': {e}"
                ) from e

    def register_lazy_resources(
        self,
        context: ExecutionContext,
        resource_names: Optional[Set[str]] = None,
    ) -> None:
        """
        Register resources for LAZY initialization.

        Resources are only initialized when first accessed via context.get_resource().

        Args:
            context: Execution context
            resource_names: Resources to register for lazy loading (defaults to all)
        """
        names = (
            resource_names
            if resource_names is not None
            else self.get_registered_names()
        )

        for name in names:
            provider = self._providers.get(name)
            if not provider:
                continue

            # Skip if already initialized
            if context.has_resource(name):
                continue

            # Create lazy wrapper
            def make_initializer(p=provider, ctx=context):
                return lambda: p.initialize(ctx)

            lazy = LazyResource(_provider_fn=make_initializer())
            context.set_lazy_resource(name, lazy, provider)

    def initialize_all(self, context: "ExecutionContext") -> None:
        """Initialize all registered resources."""
        self.initialize(context, self.get_registered_names())

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
