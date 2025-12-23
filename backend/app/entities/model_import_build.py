"""
ModelImportBuild Entity - Tracks builds fetched during model import.

This entity links fetched builds to a specific ModelRepoConfig import session,
enabling query-based tracking instead of passing state through Celery tasks.

Key design principles:
- Import session tracking: Links build to specific import version
- Status tracking: Tracks build through fetch → ingestion → processing
- Query-based flow: Enables DB queries instead of state passing
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId


class ModelImportBuildStatus(str, Enum):
    """Status of a build in the import pipeline."""

    FETCHED = "fetched"  # Build successfully fetched from CI provider
    FAILED = "failed"  # Failed to fetch


class ModelImportBuild(BaseEntity):
    """
    Tracks a build fetched during model import.

    Links RawBuildRun to ModelRepoConfig for import session tracking.
    Enables query-based flow instead of passing build IDs through tasks.
    """

    class Config:
        collection = "model_import_builds"
        use_enum_values = True

    # Link to import session
    model_repo_config_id: PyObjectId = Field(
        ...,
        description="Reference to model_repo_configs - the import session",
    )

    # Link to raw build data
    raw_build_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_build_runs - the source build data",
    )

    # Import version (to distinguish between re-imports)
    import_version: int = Field(
        default=1,
        description="Import version from ModelRepoConfig at time of fetch",
    )

    # Pipeline status
    status: ModelImportBuildStatus = Field(
        default=ModelImportBuildStatus.FETCHED,
        description="Fetch status: FETCHED or FAILED",
    )

    status_error: Optional[str] = Field(
        None,
        description="Error message if status is FAILED",
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
