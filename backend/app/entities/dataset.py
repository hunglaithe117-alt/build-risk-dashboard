from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.ci_providers.models import CIProvider

from .base import BaseEntity, PyObjectId


class DatasetValidationStatus(str, Enum):
    """Dataset validation status."""

    PENDING = "pending"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class DatasetMapping(BaseModel):
    """Mappings from dataset columns to required build identifiers."""

    build_id: Optional[str] = None
    repo_name: Optional[str] = None
    ci_provider: Optional[str] = None  # Column name for CI provider (multi-provider mode)


class DatasetStats(BaseModel):
    """Basic data quality stats for a dataset."""

    missing_rate: float = 0.0
    duplicate_rate: float = 0.0
    build_coverage: float = 0.0


class ValidationStats(BaseModel):
    """Statistics from dataset validation process."""

    repos_total: int = 0
    repos_valid: int = 0
    repos_invalid: int = 0
    repos_not_found: int = 0
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0
    builds_filtered: int = 0


class BuildValidationFilters(BaseModel):
    """Filters applied during build validation."""

    exclude_bots: bool = False
    only_completed: bool = True

    # Available: success, failure, cancelled, skipped, timed_out, action_required, neutral, stale
    allowed_conclusions: List[str] = Field(default_factory=lambda: ["success", "failure"])


class DatasetProject(BaseEntity):
    """Dataset/project metadata stored in MongoDB."""

    user_id: Optional[PyObjectId] = None
    name: str
    description: Optional[str] = None
    file_name: str
    file_path: str
    source: str = "upload"
    rows: int = 0
    size_bytes: int = 0
    columns: List[str] = Field(default_factory=list)
    mapped_fields: DatasetMapping = Field(default_factory=DatasetMapping)
    stats: DatasetStats = Field(default_factory=DatasetStats)
    preview: List[Dict[str, Any]] = Field(default_factory=list)

    # CI Provider configuration
    ci_provider: Optional[CIProvider] = Field(
        default=CIProvider.GITHUB_ACTIONS,
        description="CI provider for the dataset (None if using column mapping)",
    )
    build_filters: BuildValidationFilters = Field(
        default_factory=BuildValidationFilters,
        description="Filters applied during build validation",
    )

    # Validation status
    validation_status: DatasetValidationStatus = DatasetValidationStatus.PENDING
    validation_task_id: Optional[str] = None
    validation_started_at: Optional[datetime] = None
    validation_completed_at: Optional[datetime] = None
    validation_progress: int = 0  # 0-100
    validation_stats: ValidationStats = Field(default_factory=ValidationStats)
    validation_error: Optional[str] = None

    # Setup progress tracking (1=uploaded, 2=validated)
    setup_step: int = 1

    # Enrichment tracking
    total_versions: int = 0
    last_enriched_at: Optional[datetime] = None

    class Config:
        use_enum_values = True
