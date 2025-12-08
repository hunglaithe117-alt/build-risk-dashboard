import logging
from typing import Dict, Optional, Type

from pymongo.database import Database

from .base import CIProviderInterface
from .models import CIProvider, ProviderConfig

logger = logging.getLogger(__name__)


class CIProviderRegistry:
    """
    Registry and factory for CI providers.
    """

    _providers: Dict[CIProvider, Type[CIProviderInterface]] = {}

    @classmethod
    def register(cls, provider_type: CIProvider):
        """
        Decorator to register a CI provider implementation.

        Args:
            provider_type: The CIProvider enum value

        Returns:
            Decorator function
        """

        def decorator(provider_class: Type[CIProviderInterface]):
            cls._providers[provider_type] = provider_class
            logger.debug(f"Registered CI provider: {provider_type.value}")
            return provider_class

        return decorator

    @classmethod
    def get(
        cls,
        provider_type: CIProvider,
        config: Optional[ProviderConfig] = None,
        db: Optional[Database] = None,
    ) -> CIProviderInterface:
        """
        Get a provider instance by type.

        Args:
            provider_type: The CIProvider enum value
            config: Optional provider configuration
            db: Optional database instance for token pool (GitHub only)

        Returns:
            CIProviderInterface instance

        Raises:
            ValueError: If provider type is not registered
        """
        if provider_type not in cls._providers:
            raise ValueError(
                f"CI provider '{provider_type.value}' is not registered. "
                f"Available: {[p.value for p in cls._providers.keys()]}"
            )

        provider_class = cls._providers[provider_type]

        if config is None:
            config = ProviderConfig(provider=provider_type)

        # Pass db to GitHub provider for token pool integration
        if provider_type == CIProvider.GITHUB_ACTIONS and db is not None:
            return provider_class(config, db=db)

        return provider_class(config)

    @classmethod
    def get_all_types(cls) -> list[CIProvider]:
        """Get list of all registered provider types."""
        return list(cls._providers.keys())

    @classmethod
    def is_registered(cls, provider_type: CIProvider) -> bool:
        """Check if a provider type is registered."""
        return provider_type in cls._providers


def get_ci_provider(
    provider_type: CIProvider,
    config: Optional[ProviderConfig] = None,
    db: Optional[Database] = None,
) -> CIProviderInterface:
    """Get a CI provider instance by type."""
    return CIProviderRegistry.get(provider_type, config, db=db)
