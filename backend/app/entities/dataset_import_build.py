"""
DatasetImportBuild Entity - Tracks builds through the dataset ingestion pipeline.

This entity links builds to a DatasetVersion and tracks their progress
through ingestion stages (clone → worktree → logs).

Key design principles:
- Version tracking: Links build to DatasetVersion
- Status tracking: Tracks build through PENDING → INGESTING → INGESTED
- Per-resource tracking: Extensible resource_status dict for granular error tracking
- Query-based flow: Enables DB queries instead of state passing
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.entities.base import BaseEntity, PyObjectId


class DatasetImportBuildStatus(str, Enum):
    """Status of a build in the dataset ingestion pipeline."""

    # Initial state
    PENDING = "pending"  # Queued for ingestion

    # Ingestion stage (clone, worktree, logs)
    INGESTING = "ingesting"  # Ingestion in progress
    INGESTED = "ingested"  # Resources ready for enrichment

    # Missing resources (graceful degradation - can still process)
    MISSING_RESOURCE = "missing_resource"  # Some resources unavailable but can still process


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


class DatasetImportBuild(BaseEntity):
    """
    Tracks a build through the dataset ingestion pipeline.

    Links DatasetBuild (CSV row) to DatasetVersion for ingestion tracking.
    Tracks status from pending through ingestion stages.
    """

    class Config:
        collection = "dataset_import_builds"
        use_enum_values = True

    # Parent references
    dataset_version_id: PyObjectId = Field(
        ...,
        description="Reference to dataset_versions",
    )

    dataset_build_id: PyObjectId = Field(
        ...,
        description="Reference to dataset_builds (CSV row)",
    )

    # Raw data references
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories",
    )

    raw_build_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_build_runs - the source build data",
    )

    # Pipeline status
    status: DatasetImportBuildStatus = Field(
        default=DatasetImportBuildStatus.PENDING,
        description="Pipeline status: PENDING → INGESTING → INGESTED or MISSING_RESOURCE",
    )

    # Per-resource status tracking (extensible)
    resource_status: Dict[str, ResourceStatusEntry] = Field(
        default_factory=dict,
        description="Per-resource status. Keys: 'clone', 'worktree', 'logs', etc.",
    )

    # Required resources for this build
    required_resources: List[str] = Field(
        default_factory=list,
        description="Resources required for this build",
    )

    # Denormalized fields for quick access (avoid joins)
    ci_run_id: str = Field(
        default="",
        description="CI run ID (denormalized from RawBuildRun)",
    )

    commit_sha: str = Field(
        default="",
        description="Commit SHA (denormalized from RawBuildRun)",
    )

    repo_full_name: str = Field(
        default="",
        description="Repository full name (denormalized)",
    )

    # Timestamps for tracking
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this import build was created",
    )

    ingestion_started_at: Optional[datetime] = Field(
        None,
        description="When ingestion started",
    )

    ingested_at: Optional[datetime] = Field(
        None,
        description="When ingestion completed successfully",
    )
