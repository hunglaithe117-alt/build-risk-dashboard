from datetime import datetime
from typing import Optional

from .base import PyObjectId
from .base_repository import BaseRepositoryEntity, RepoValidationStatus


class EnrichmentRepository(BaseRepositoryEntity):
    dataset_id: PyObjectId
    validation_status: RepoValidationStatus = RepoValidationStatus.PENDING
    validation_error: Optional[str] = None
    validated_at: Optional[datetime] = None
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0

    class Config:
        collection = "enrichment_repositories"
