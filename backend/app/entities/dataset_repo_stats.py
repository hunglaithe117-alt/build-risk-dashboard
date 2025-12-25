from typing import Optional

from pydantic import Field

from app.ci_providers.models import CIProvider
from app.entities.base import BaseEntity, PyObjectId


class DatasetRepoStats(BaseEntity):
    """Per-repository stats for a dataset. Stored in separate collection."""

    class Config:
        collection = "dataset_repo_stats"

    # References
    dataset_id: PyObjectId
    raw_repo_id: PyObjectId  # Link to RawRepository

    # Repo info (denormalized for convenience)
    full_name: str

    # CI Provider config
    ci_provider: CIProvider = Field(default=CIProvider.GITHUB_ACTIONS)

    # Validation stats
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0
    builds_filtered: int = 0
    is_valid: bool = True
    validation_error: Optional[str] = None
