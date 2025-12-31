"""
ModelImportBuild Entity - Tracks builds through the import pipeline.

This entity links builds to a ModelRepoConfig and tracks their progress
through fetch → ingestion → processing stages.

Key design principles:
- Session tracking: Links build to ModelRepoConfig
- Status tracking: Tracks build through fetch → ingestion → processing
- Query-based flow: Enables DB queries instead of state passing
- Per-resource tracking: Extensible resource_status dict for granular error tracking
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.entities.base import BaseEntity, PyObjectId


class ModelImportBuildStatus(str, Enum):
    """Status of a build in the import pipeline."""

    # Initial state
    PENDING = "pending"  # Queued for fetch

    # Fetch stage
    FETCHED = "fetched"  # Build info fetched from CI API

    # Ingestion stage (clone, worktree, logs)
    INGESTING = "ingesting"  # Ingestion in progress
    INGESTED = "ingested"  # Resources ready for processing

    # Missing resources (graceful degradation)
    MISSING_RESOURCE = "missing_resource"  # Some resources unavailable (logs, worktree, etc.)


class ResourceStatus(str, Enum):
    """Status of a single resource in ingestion."""

    PENDING = "pending"  # Not started
    IN_PROGRESS = "in_progress"  # Currently being fetched/created
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Failed with error
    SKIPPED = "skipped"  # Not required by template


class ResourceStatusEntry(BaseModel):
    """Status entry for a single resource."""

    status: ResourceStatus = ResourceStatus.PENDING
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ModelImportBuild(BaseEntity):
    """
    Tracks a build through the import pipeline.

    Links RawBuildRun to ModelRepoConfig for import session tracking.
    Tracks status from fetch through ingestion to processing.
    """

    class Config:
        collection = "model_import_builds"
        use_enum_values = True

    model_repo_config_id: PyObjectId = Field(
        ...,
        description="Reference to model_repo_configs",
    )

    # Link to raw build data
    raw_build_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_build_runs - the source build data",
    )

    # Pipeline status
    status: ModelImportBuildStatus = Field(
        default=ModelImportBuildStatus.FETCHED,
        description="Pipeline status: FETCHED → INGESTING → INGESTED or FAILED",
    )

    # Per-resource status tracking (extensible)
    resource_status: Dict[str, ResourceStatusEntry] = Field(
        default_factory=dict,
        description="Per-resource status. Keys: 'clone', 'worktree', 'logs', etc.",
    )

    # Required resources for this build (from template)
    required_resources: List[str] = Field(
        default_factory=list,
        description="Resources required by template for this build",
    )

    # Denormalized fields for quick access (avoid joins)
    ci_run_id: str = Field(
        ...,
        description="CI run ID (denormalized from RawBuildRun)",
    )

    commit_sha: str = Field(
        default="",
        description="Commit SHA (denormalized from RawBuildRun)",
    )

    # Timestamps for tracking
    fetched_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this build was fetched from CI provider",
    )

    ingestion_started_at: Optional[datetime] = Field(
        None,
        description="When ingestion started",
    )

    ingested_at: Optional[datetime] = Field(
        None,
        description="When ingestion completed successfully",
    )
