"""
DatasetVersion Entity - Tracks versions of enriched datasets.

Each version represents a unique enrichment run with specific feature selections.
One dataset can have multiple versions with different feature sets.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import Field

from app.entities.base import BaseEntity


class VersionStatus(str, Enum):
    """Dataset version status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DatasetVersion(BaseEntity):
    """
    Represents a version of an enriched dataset.

    Each version has a unique combination of selected features.
    Users can create multiple versions from the same dataset
    with different feature selections.
    """

    class Config:
        collection_name = "dataset_versions"
        use_enum_values = True

    # Version identification
    dataset_id: str = Field(..., description="ID of the parent dataset")
    user_id: str = Field(..., description="User who created this version")
    version_number: int = Field(..., description="Auto-incremented version number")
    name: str = Field(default="", description="User-provided or auto-generated name")
    description: Optional[str] = Field(None, description="Optional description")

    # Feature selection
    selected_features: List[str] = Field(
        default_factory=list, description="List of selected feature names"
    )
    selected_sources: List[str] = Field(
        default_factory=list,
        description="List of data sources used (git, build_log, github, etc.)",
    )

    # Status
    status: VersionStatus = VersionStatus.PENDING

    # Progress tracking
    total_rows: int = Field(default=0, description="Total rows to process")
    processed_rows: int = Field(default=0, description="Rows processed so far")
    enriched_rows: int = Field(default=0, description="Rows successfully enriched")
    failed_rows: int = Field(default=0, description="Rows that failed enrichment")
    skipped_rows: int = Field(default=0, description="Rows skipped (already processed)")

    # Auto-import tracking
    repos_auto_imported: List[str] = Field(
        default_factory=list,
        description="Repositories that were auto-imported during enrichment",
    )
    repos_failed_import: List[str] = Field(
        default_factory=list, description="Repositories that failed to import"
    )

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error handling
    error_message: Optional[str] = None
    row_errors: List[dict] = Field(
        default_factory=list, description="List of {row_index, error} for failed rows"
    )

    # Output file
    file_path: Optional[str] = Field(None, description="Path to the enriched CSV file")
    file_name: Optional[str] = Field(None, description="Original filename for download")
    file_size_bytes: Optional[int] = Field(None, description="Size of output file")

    # Celery task tracking
    task_id: Optional[str] = None

    # --- Methods ---

    def mark_started(self) -> None:
        """Mark version as started processing."""
        self.status = VersionStatus.PROCESSING
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self, file_path: str, file_size: int) -> None:
        """Mark version as completed."""
        self.status = VersionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.file_path = file_path
        self.file_size_bytes = file_size

    def mark_failed(self, error: str) -> None:
        """Mark version as failed."""
        self.status = VersionStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)

    def mark_cancelled(self) -> None:
        """Mark version as cancelled."""
        self.status = VersionStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc)

    def increment_progress(
        self,
        success: bool = True,
        error: Optional[str] = None,
        row_index: Optional[int] = None,
    ) -> None:
        """Increment progress counters."""
        self.processed_rows += 1
        if success:
            self.enriched_rows += 1
        else:
            self.failed_rows += 1
            if error and row_index is not None:
                self.row_errors.append({"row_index": row_index, "error": error})

    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_rows == 0:
            return 0.0
        return (self.processed_rows / self.total_rows) * 100

    @property
    def is_complete(self) -> bool:
        """Check if version is in a terminal state."""
        return self.status in (
            VersionStatus.COMPLETED,
            VersionStatus.FAILED,
            VersionStatus.CANCELLED,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate processing duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def generate_default_name(self) -> str:
        """Generate a default name based on selected sources."""
        if not self.selected_sources:
            return f"v{self.version_number}"

        source_names = {
            "git": "Git",
            "github": "GitHub",
            "build_log": "Build Logs",
            "sonarqube": "SonarQube",
            "trivy": "Trivy",
            "repo": "Repo",
        }

        source_labels = [source_names.get(s, s.title()) for s in self.selected_sources]
        return f"v{self.version_number} - {' + '.join(source_labels)}"
