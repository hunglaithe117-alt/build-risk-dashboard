"""
ModelRepoConfig Entity - Configuration for ML model training data pipeline.

This entity stores settings for repositories imported for ML model training.
Flow: GitHub import → Build ingestion → Feature extraction → Model training
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from app.entities.base import PyObjectId
from app.entities.repo_config_base import FeatureConfigBase


class ModelImportStatus(str, Enum):
    """Status of the model repository import process."""

    QUEUED = "queued"
    FETCHING = "fetching"  # Fetching builds from CI API
    INGESTING = "ingesting"  # Clone/worktree/download logs phase
    INGESTED = "ingested"  # Ingestion done (user accepts current state to start processing)
    PROCESSING = "processing"  # Feature extraction phase
    PROCESSED = "processed"  # Processing complete (features extracted)
    FAILED = "failed"  # Critical error, pipeline failed


class ModelRepoConfig(FeatureConfigBase):
    class Config:
        collection = "model_repo_configs"
        use_enum_values = True

    # === IDENTITY ===
    full_name: str = Field(
        ...,
        description="Full repository name (e.g., 'owner/repo')",
    )
    ci_provider: str = Field(
        ...,
        description="CI/CD provider name (e.g., github_actions, travis_ci)",
    )
    user_id: PyObjectId = Field(
        ...,
        description="User who owns this configuration",
    )
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )

    # === IMPORT CONSTRAINTS (configurable) ===
    max_builds_to_ingest: Optional[int] = Field(
        None,
        description="Maximum number of builds to import (None = unlimited)",
    )
    since_days: Optional[int] = Field(
        None,
        description="Only import builds from last N days (None = all time)",
    )
    only_with_logs: bool = Field(
        default=False,
        description="Only import builds that have downloadable logs",
    )

    # === STATUS (unified) ===
    status: ModelImportStatus = Field(
        default=ModelImportStatus.QUEUED,
        description="Pipeline status: queued/ingesting/processing/imported/failed",
    )
    error_message: Optional[str] = Field(
        None,
        description="Error message if pipeline failed",
    )

    # === TIMESTAMPS ===
    started_at: Optional[datetime] = Field(
        None,
        description="When the import process started",
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="When the import process completed",
    )
    last_synced_at: Optional[datetime] = Field(
        None,
        description="Last successful sync timestamp (for incremental updates)",
    )
    latest_run_created_at: Optional[datetime] = Field(
        None,
        description="Creation time of the latest workflow run synced (cursor for incremental sync)",
    )

    # === STATS ===
    builds_fetched: int = Field(
        default=0,
        description="Number of builds fetched from CI API",
    )
    builds_ingested: int = Field(
        default=0,
        description="Number of builds ingested (logs downloaded, worktrees created)",
    )
    builds_completed: int = Field(
        default=0,
        description="Number of builds completed (extraction + prediction)",
    )

    # Ingestion phase counter
    builds_missing_resource: int = Field(
        default=0,
        description="Number of builds with missing resources during ingestion (logs, worktree)",
    )

    # Processing phase counter (extraction + prediction failures)
    builds_processing_failed: int = Field(
        default=0,
        description="Number of builds that failed during processing (extraction or prediction)",
    )

    last_processed_import_build_id: Optional[PyObjectId] = Field(
        None,
        description="ObjectId of the last ModelImportBuild that was processed. "
        "Builds with _id > this value are pending processing.",
    )
