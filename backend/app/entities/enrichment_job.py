"""
EnrichmentJob Entity - Tracks dataset enrichment jobs.

An enrichment job processes CSV rows to extract build commit features
using the mini-Airflow pipeline.
"""

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import Field

from app.entities.base import BaseEntity


class EnrichmentJob(BaseEntity):
    """
    Represents a dataset enrichment job.

    Enrichment jobs process uploaded CSV datasets to:
    1. Auto-import missing repositories
    2. Create BuildSample records for each row
    3. Run the feature extraction pipeline
    4. Save enriched features to database
    5. Generate downloadable enriched CSV
    """

    class Config:
        collection_name = "enrichment_jobs"

    # Job identification
    dataset_id: str = Field(..., description="ID of the dataset being enriched")
    user_id: str = Field(..., description="User who started the job")

    # Status
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = Field(
        default="pending"
    )

    # Progress tracking
    total_rows: int = Field(default=0, description="Total rows in CSV")
    processed_rows: int = Field(default=0, description="Rows processed so far")
    enriched_rows: int = Field(default=0, description="Rows successfully enriched")
    failed_rows: int = Field(default=0, description="Rows that failed enrichment")
    skipped_rows: int = Field(default=0, description="Rows skipped (already processed)")

    # Configuration
    selected_features: List[str] = Field(default_factory=list)

    # Auto-import tracking
    repos_auto_imported: List[str] = Field(
        default_factory=list,
        description="Repositories that were auto-imported during enrichment"
    )
    repos_failed_import: List[str] = Field(
        default_factory=list,
        description="Repositories that failed to import"
    )

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error handling
    error: Optional[str] = None
    row_errors: List[dict] = Field(
        default_factory=list,
        description="List of {row_index, error} for failed rows"
    )

    # Output
    output_file: Optional[str] = Field(
        None,
        description="Path to the enriched CSV file"
    )

    # Celery task tracking
    celery_task_id: Optional[str] = None

    def mark_started(self) -> None:
        """Mark job as started."""
        self.status = "running"
        self.started_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Mark job as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str) -> None:
        """Mark job as failed."""
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now(timezone.utc)

    def mark_cancelled(self) -> None:
        """Mark job as cancelled."""
        self.status = "cancelled"
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
        """Check if job is in a terminal state."""
        return self.status in ("completed", "failed", "cancelled")

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds."""
        if not self.started_at:
            return None
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()
