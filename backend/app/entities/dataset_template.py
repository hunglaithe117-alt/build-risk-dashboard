from typing import Any, Dict, List, Optional

from pydantic import Field

from .base import BaseEntity
from .dataset import DatasetMapping, DatasetStats


class DatasetTemplate(BaseEntity):
    """Template metadata for datasets shipped with the product."""

    name: str
    description: Optional[str] = None
    file_name: str
    source: str = "seed"
    rows: int = 0
    size_mb: float = 0.0
    columns: List[str] = Field(default_factory=list)
    mapped_fields: DatasetMapping = Field(default_factory=DatasetMapping)
    stats: DatasetStats = Field(default_factory=DatasetStats)
    tags: List[str] = Field(default_factory=list)
    selected_template: Optional[str] = None
    selected_features: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)
