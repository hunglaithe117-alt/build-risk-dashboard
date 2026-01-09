"""
DatasetVersion Entity - Tracks versions of enriched datasets.

Each version represents a unique enrichment run with specific feature selections.
One dataset can have multiple versions with different feature sets.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import Field

from app.entities.base import PyObjectId
from app.entities.repo_config_base import FeatureConfigBase


class VersionStatus(str, Enum):
    """Dataset version status"""

    QUEUED = "queued"  # Initial state, waiting to start
    INGESTING = "ingesting"  # Clone/worktree/download logs phase
    INGESTED = "ingested"  # Ingestion done, waiting for user to start processing
    PROCESSING = "processing"  # Feature extraction phase
    PROCESSED = "processed"  # Processing complete (features extracted)
    FAILED = "failed"  # Critical error, pipeline failed


class DatasetVersion(FeatureConfigBase):
    class Config:
        collection_name = "dataset_versions"
        use_enum_values = True

    dataset_id: PyObjectId = Field(..., description="ID of the parent dataset")
    user_id: PyObjectId = Field(..., description="User who created this version")
    version_number: int = Field(..., description="Auto-incremented version number")
    name: str = Field(default="", description="User-provided or auto-generated name")
    description: Optional[str] = Field(None, description="Optional description")

    selected_features: List[str] = Field(
        default_factory=list, description="List of selected feature names"
    )

    # Scan metrics to include in features (from SonarQube/Trivy)
    scan_metrics: dict = Field(
        default_factory=lambda: {"sonarqube": [], "trivy": []},
        description="Selected scan metrics: {'sonarqube': [...], 'trivy': [...]}",
    )

    # Scan tool configuration (SonarQube/Trivy settings)
    scan_config: dict = Field(
        default_factory=lambda: {"sonarqube": {}, "trivy": {}},
        description="Scan tool config: {'sonarqube': {...}, 'trivy': {...}}",
    )

    status: VersionStatus = VersionStatus.QUEUED

    # === BUILD STATS ===
    builds_total: int = Field(default=0, description="Total validated builds in version")
    builds_ingested: int = Field(default=0, description="Builds with resources prepared")
    builds_missing_resource: int = Field(
        default=0, description="Builds with missing resources (not retryable)"
    )
    builds_ingestion_failed: int = Field(
        default=0, description="Builds that failed with actual errors (retryable)"
    )
    builds_features_extracted: int = Field(default=0, description="Builds with features extracted")
    builds_extraction_failed: int = Field(
        default=0, description="Builds that failed during feature extraction"
    )

    # === SCAN TRACKING ===
    scans_total: int = Field(
        default=0, description="Total scans to run (unique commits × enabled tools)"
    )
    scans_completed: int = Field(default=0, description="Completed scans")
    scans_failed: int = Field(default=0, description="Failed scans")

    # === COMPLETION FLAGS ===
    feature_extraction_completed: bool = Field(default=False, description="All features extracted")
    scan_extraction_completed: bool = Field(
        default=False, description="All scans done (completed + failed = total)"
    )
    enrichment_notified: bool = Field(
        default=False, description="Enrichment complete notification sent"
    )

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    error_message: Optional[str] = None

    task_id: Optional[str] = None

    def mark_started(self) -> None:
        """Mark version as started processing."""
        self.status = VersionStatus.PROCESSING
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Mark version as completed."""
        self.status = VersionStatus.PROCESSED
        self.completed_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        """Mark version as failed."""
        self.status = VersionStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)

    @property
    def progress_percent(self) -> float:
        """Calculate processing progress percentage."""
        if self.builds_total == 0:
            return 0.0
        return (self.builds_features_extracted / self.builds_total) * 100

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate processing duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def generate_default_name(self) -> str:
        return f"v{self.version_number}_{self.name}"
