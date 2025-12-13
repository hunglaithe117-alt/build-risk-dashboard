"""Model Repository entity - for Bayesian model training flow."""

from datetime import datetime
from typing import Optional

from .base import PyObjectId
from .base_repository import (
    BaseRepositoryEntity,
    ImportStatus,
    Provider,
    SyncStatus,
)


class ModelRepository(BaseRepositoryEntity):
    user_id: PyObjectId
    provider: Provider = Provider.GITHUB

    import_status: ImportStatus = ImportStatus.QUEUED
    total_builds_imported: int = 0
    last_scanned_at: datetime | None = None
    last_sync_error: str | None = None
    notes: str | None = None

    last_synced_at: Optional[datetime] = None
    last_sync_status: Optional[SyncStatus] = None
    latest_synced_run_created_at: datetime | None = None

    max_builds_to_ingest: Optional[int] = None

    class Config:
        collection = "model_repositories"
        use_enum_values = True
