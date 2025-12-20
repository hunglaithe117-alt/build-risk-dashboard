"""
RepoConfigBase - Common configuration fields shared by repo config entities.

This base class centralizes user-configurable settings used by both:
- ModelRepoConfig (Flow 1)
- DatasetRepoConfig (Flow 2)

Design:
- Extends BaseEntity for common metadata
- Contains only shared configuration fields
"""

from typing import Any, Dict

from pydantic import Field

from app.entities.base import BaseEntity


class FeatureConfigBase(BaseEntity):
    """
    Common configuration for feature extraction.

    Includes shared, user-configurable settings such as languages,
    test frameworks
    """

    feature_configs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Feature extractors to run",
    )
