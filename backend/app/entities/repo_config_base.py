"""
RepoConfigBase - Common configuration fields shared by repo config entities.

This base class centralizes user-configurable settings used by both:
- ModelRepoConfig (Flow 1)
- DatasetRepoConfig (Flow 2)

Design:
- Extends BaseEntity for common metadata
- Contains only shared configuration fields
"""

from typing import List

from pydantic import Field

from app.ci_providers.models import CIProvider
from app.entities.base import BaseEntity
from app.entities.enums import TestFramework


class RepoConfigBase(BaseEntity):
    """
    Common configuration for repository-related entities.

    Includes shared, user-configurable settings such as languages,
    test frameworks, and CI provider.
    """

    # User-configurable settings
    source_languages: List[str] = Field(
        default_factory=list,
        description="Programming languages for this repository",
    )

    test_frameworks: List[TestFramework] = Field(
        default_factory=list,
        description="Test frameworks",
    )

    ci_provider: CIProvider = Field(
        default=CIProvider.GITHUB_ACTIONS,
        description="CI/CD provider",
    )
