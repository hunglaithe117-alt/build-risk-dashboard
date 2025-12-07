from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import BaseEntity, PyObjectId


class DatasetMapping(BaseModel):
    """Mappings from dataset columns to required build identifiers."""

    build_id: Optional[str] = None
    commit_sha: Optional[str] = None
    repo_name: Optional[str] = None
    timestamp: Optional[str] = None


class DatasetStats(BaseModel):
    """Basic data quality stats for a dataset."""

    coverage: float = 0.0
    missing_rate: float = 0.0
    duplicate_rate: float = 0.0
    build_coverage: float = 0.0


class DatasetProject(BaseEntity):
    """Dataset/project metadata stored in MongoDB."""

    user_id: Optional[PyObjectId] = None
    name: str
    description: Optional[str] = None
    file_name: str
    source: str = "upload"
    rows: int = 0
    size_mb: float = 0.0
    columns: List[str] = Field(default_factory=list)
    mapped_fields: DatasetMapping = Field(default_factory=DatasetMapping)
    stats: DatasetStats = Field(default_factory=DatasetStats)
    tags: List[str] = Field(default_factory=list)
    selected_template: Optional[str] = None
    selected_features: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)
