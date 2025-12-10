from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import BaseEntity, PyObjectId
from app.ci_providers.models import CIProvider


class DatasetMapping(BaseModel):
    """Mappings from dataset columns to required build identifiers."""

    build_id: Optional[str] = None
    repo_name: Optional[str] = None


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
    ci_provider: CIProvider = Field(
        default=CIProvider.GITHUB_ACTIONS,
        description="CI/CD provider for build data",
    )
    rows: int = 0
    size_bytes: int = 0
    columns: List[str] = Field(default_factory=list)
    mapped_fields: DatasetMapping = Field(default_factory=DatasetMapping)
    stats: DatasetStats = Field(default_factory=DatasetStats)
    selected_features: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)
