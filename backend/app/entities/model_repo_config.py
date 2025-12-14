"""
ModelRepoConfig Entity - User-specific configuration for ML model training flow.

This entity stores user preferences and settings for repositories imported
for ML model training purposes (Flow 1: GitHub import → Model training).

Key design principles:
- User-specific: Each user can have different configs for the same repository
- Configuration only: No raw GitHub data, only user preferences
- References raw_repository: Links to the immutable raw data
"""

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.entities.base import PyObjectId
from app.entities.enums import ModelImportStatus, ModelSyncStatus
from app.entities.repo_config_base import RepoConfigBase


class ModelRepoConfig(RepoConfigBase):
    """
    User configuration for a repository in the model training flow.

    This represents a user's decision to track a repository for ML training.
    The same raw_repository can have multiple configs (different users).
    """

    class Config:
        collection = "model_repo_configs"
        use_enum_values = True

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

    # User-configurable settings inherited from RepoConfigBase

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

    # GitHub App installation
    installation_id: Optional[str] = Field(
        None,
        description="GitHub App installation ID for private repos",
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
        description="Number of builds that failed to import",
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

    # Soft delete
    is_deleted: bool = Field(
        default=False,
        description="Soft delete flag (keep history)",
    )
    deleted_at: Optional[datetime] = Field(
        None,
        description="When this config was deleted",
    )
