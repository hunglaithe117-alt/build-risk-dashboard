from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import BaseEntity, PyObjectId
from app.ci_providers.models import CIProvider


class DatasetValidationStatus(str, Enum):
    """Dataset validation status."""

    PENDING = "pending"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DatasetIngestionStatus(str, Enum):
    """Dataset ingestion status (resource collection)."""

    PENDING = "pending"
    INGESTING = "ingesting"
    COMPLETED = "completed"
    FAILED = "failed"


class DatasetMapping(BaseModel):
    """Mappings from dataset columns to required build identifiers."""

    build_id: Optional[str] = None
    repo_name: Optional[str] = None


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


class IngestionStats(BaseModel):
    """Statistics from dataset ingestion process."""

    repos_total: int = 0
    repos_ingested: int = 0
    repos_failed: int = 0
    builds_total: int = 0
    worktrees_created: int = 0
    logs_downloaded: int = 0


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
    source_languages: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)
    preview: List[Dict[str, Any]] = Field(default_factory=list)

    # Validation status
    validation_status: DatasetValidationStatus = DatasetValidationStatus.PENDING
    validation_task_id: Optional[str] = None
    validation_started_at: Optional[datetime] = None
    validation_completed_at: Optional[datetime] = None
    validation_progress: int = 0  # 0-100
    validation_stats: ValidationStats = Field(default_factory=ValidationStats)
    validation_error: Optional[str] = None

    # Ingestion status (resource collection after validation)
    ingestion_status: DatasetIngestionStatus = DatasetIngestionStatus.PENDING
    ingestion_task_id: Optional[str] = None
    ingestion_started_at: Optional[datetime] = None
    ingestion_completed_at: Optional[datetime] = None
    ingestion_progress: int = 0  # 0-100
    ingestion_stats: IngestionStats = Field(default_factory=IngestionStats)
    ingestion_error: Optional[str] = None

    # Setup progress tracking (1=uploaded, 2=configured, 3=validated, 4=ingested)
    setup_step: int = 1

    # Enrichment tracking
    total_versions: int = 0
    last_enriched_at: Optional[datetime] = None

    class Config:
        use_enum_values = True
