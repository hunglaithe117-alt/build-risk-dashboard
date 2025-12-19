"""
DatasetRepoConfig Entity - Repository configuration within a dataset.

This entity stores configuration for repositories discovered during
dataset validation (Flow 2: Dataset upload → Repository validation).

Key design principles:
- Top-level entity: Stored in its own collection with dataset_id reference
- Dataset-specific: Configuration applies to this dataset only
- References raw_repository: Links to the immutable raw data
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.entities.base import PyObjectId
from app.entities.enums import DatasetRepoValidationStatus
from app.entities.repo_config_base import RepoConfigBase


class DatasetRepoConfig(RepoConfigBase):
    """
    Configuration for a repository discovered in a dataset.

    This is stored as a separate collection with reference to dataset_id.
    It links CSV data to actual GitHub repositories and stores user preferences.
    """

    class Config:
        collection = "dataset_repo_configs"
        use_enum_values = True

    # Reference to dataset
    dataset_id: PyObjectId = Field(
        ...,
        description="Reference to datasets table",
    )

    # Reference to raw repository (None for invalid/not found repos)
    raw_repo_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to raw_repositories._id (None if repo validation failed)",
    )

    # Validation status
    validation_status: DatasetRepoValidationStatus = Field(
        default=DatasetRepoValidationStatus.PENDING,
        description="Current validation status",
    )
    validation_error: Optional[str] = Field(
        None,
        description="Error message if validation failed",
    )
    validated_at: Optional[datetime] = Field(
        None,
        description="When validation completed",
    )

    # User-configurable settings inherited from RepoConfigBase

    # Build statistics from CSV
    builds_in_csv: int = Field(
        default=0,
        description="Number of builds for this repo in the CSV",
    )
    builds_found: int = Field(
        default=0,
        description="Number of builds successfully matched to GitHub",
    )
    builds_not_found: int = Field(
        default=0,
        description="Number of builds that couldn't be found",
    )
    builds_processed: int = Field(
        default=0,
        description="Number of builds with extracted features",
    )
