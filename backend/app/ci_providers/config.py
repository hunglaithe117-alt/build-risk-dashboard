from app.config import settings

from .models import CIProvider, ProviderConfig


def get_provider_config(provider_type: CIProvider) -> ProviderConfig:
    """
    Get ProviderConfig for a CI provider using app settings.

    Args:
        provider_type: The CI provider type

    Returns:
        ProviderConfig populated with settings
    """
    if provider_type == CIProvider.GITHUB_ACTIONS:
        # GitHub uses token pool, get first available token
        token = settings.GITHUB_TOKENS[0] if settings.GITHUB_TOKENS else None
        return ProviderConfig(
            provider=provider_type,
            token=token,
            base_url=settings.GITHUB_API_URL,
        )

    elif provider_type == CIProvider.GITLAB_CI:
        return ProviderConfig(
            provider=provider_type,
            token=settings.GITLAB_TOKEN,
            base_url=settings.GITLAB_BASE_URL,
        )

    elif provider_type == CIProvider.JENKINS:
        return ProviderConfig(
            provider=provider_type,
            base_url=settings.JENKINS_URL,
            username=settings.JENKINS_USERNAME,
            token=settings.JENKINS_TOKEN,
        )

    elif provider_type == CIProvider.CIRCLECI:
        return ProviderConfig(
            provider=provider_type,
            token=settings.CIRCLECI_TOKEN,
            base_url=settings.CIRCLECI_BASE_URL,
        )

    elif provider_type == CIProvider.TRAVIS_CI:
        return ProviderConfig(
            provider=provider_type,
            token=settings.TRAVIS_TOKEN,
            base_url=settings.TRAVIS_BASE_URL,
        )

    return ProviderConfig(provider=provider_type)


def get_configured_provider(provider_type: CIProvider):
    """
    Get a fully configured CI provider instance.

    Args:
        provider_type: The CI provider type

    Returns:
        CIProviderInterface instance ready to use
    """
    from .factory import get_ci_provider

    config = get_provider_config(provider_type)
    return get_ci_provider(provider_type, config)
