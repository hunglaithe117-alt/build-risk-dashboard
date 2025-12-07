from typing import List, Optional

from pydantic import Field

from .base import BaseEntity


class DatasetTemplate(BaseEntity):
    """Template for predefined feature sets to apply during repo import."""

    name: str
    description: Optional[str] = None
    feature_names: List[str] = Field(
        default_factory=list
    )  # Feature names from registry
    tags: List[str] = Field(default_factory=list)
    source: str = "seed"  # "seed" or "custom"
