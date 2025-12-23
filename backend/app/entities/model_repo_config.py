"""
ModelRepoConfig Entity - User-specific configuration for ML model training flow.

This entity stores user preferences and settings for repositories imported
for ML model training purposes (Flow 1: GitHub import → Model training).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.entities.base import PyObjectId
from app.entities.enums import ModelImportStatus, ModelSyncStatus
from app.entities.repo_config_base import FeatureConfigBase


class ModelRepoConfig(FeatureConfigBase):
    class Config:
        collection = "model_repo_configs"
        use_enum_values = True

    # Repository identification (needed for querying)
    full_name: str = Field(
        ...,
        description="Full repository name (e.g., 'owner/repo')",
    )

    ci_provider: str = Field(
        ...,
        description="CI/CD provider name (e.g., github_actions, travis_ci)",
    )

    # User ownership
    user_id: PyObjectId = Field(
        ...,
        description="User who owns this configuration",
    )

    # Reference to raw repository
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )

    # Import tracking
    import_version: int = Field(
        default=1,
        description="Version number for this import (increments with each re-import)",
    )

    # Import constraints
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

    # Import status tracking
    import_status: ModelImportStatus = Field(
        default=ModelImportStatus.QUEUED,
        description="Current import status",
    )
    import_started_at: Optional[datetime] = Field(
        None,
        description="When the import process started",
    )
    import_completed_at: Optional[datetime] = Field(
        None,
        description="When the import process completed",
    )
    import_error: Optional[str] = Field(
        None,
        description="Error message if import failed",
    )

    # Import statistics
    total_builds_imported: int = Field(
        default=0,
        description="Total number of builds successfully imported",
    )
    total_builds_failed: int = Field(
        default=0,
        description="Number of builds that failed to extract",
    )
    total_builds_processed: int = Field(
        default=0,
        description="Number of builds with extracted features",
    )

    # Sync tracking (for incremental updates)
    last_synced_at: Optional[datetime] = Field(
        None,
        description="Last successful sync timestamp",
    )
    last_sync_status: Optional[ModelSyncStatus] = Field(
        None,
        description="Status of the last sync",
    )
    last_sync_error: Optional[str] = Field(
        None,
        description="Error message from last sync",
    )
    latest_synced_run_created_at: Optional[datetime] = Field(
        None,
        description="Creation time of the latest workflow run we've synced",
    )

    feature_extractors: List[str] = Field(
        default_factory=list,
        description="Specific feature extractors to run (empty = all)",
    )
