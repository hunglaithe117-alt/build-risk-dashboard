from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field

from .base import BaseEntity, PyObjectId
from app.ci_providers.models import CIProvider


class EnrichmentImportStatus(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    FAILED = "failed"


class RepoValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    ERROR = "error"


class EnrichmentRepository(BaseEntity):
    dataset_id: PyObjectId
    full_name: str  # e.g., "owner/repo"
    ci_provider: CIProvider = CIProvider.GITHUB_ACTIONS
    validation_status: RepoValidationStatus = RepoValidationStatus.PENDING
    validation_error: Optional[str] = None
    validated_at: Optional[datetime] = None
    github_repo_id: Optional[int] = None
    default_branch: Optional[str] = None
    is_private: bool = False
    builds_total: int = 0
    builds_found: int = 0
    builds_not_found: int = 0
    source_languages: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)

    class Config:
        collection = "enrichment_repositories"
