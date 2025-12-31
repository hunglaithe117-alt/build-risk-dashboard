"""Repository DTOs"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.ci_providers.models import CIProvider
from app.entities import TestFramework
from app.entities.base import PyObjectIdStr


class RepoImportRequest(BaseModel):
    full_name: str = Field(..., description="Repository full name (e.g., owner/name)")
    feature_configs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Feature configuration dict with global and per-repo settings",
    )

    ci_provider: CIProvider = Field(
        default=CIProvider.GITHUB_ACTIONS,
        description="CI/CD provider: github_actions, circleci, travis_ci",
    )
    max_builds: Optional[int] = Field(
        default=None,
        ge=1,
        le=1000,
        description="Max number of latest workflow runs/builds to ingest",
    )
    since_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Only ingest builds from the last N days",
    )
    only_with_logs: bool = Field(
        default=False,
        description="Only ingest builds that still have logs available",
    )


class RepoResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
    user_id: Optional[PyObjectIdStr] = None
    provider: str = "github"
    full_name: str
    default_branch: Optional[str] = None
    is_private: bool = False
    main_lang: Optional[str] = None
    github_repo_id: Optional[int] = None
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    ci_provider: CIProvider = CIProvider.GITHUB_ACTIONS
    test_frameworks: List[TestFramework] = Field(default_factory=list)
    source_languages: List[str] = Field(default_factory=list)
    builds_fetched: int = 0
    builds_ingested: int = 0
    builds_completed: int = 0
    builds_missing_resource: int = 0  # Ingestion phase failures
    builds_processing_failed: int = 0  # Processing phase failures
    status: Optional[str] = Field(
        default="imported",
        description="Pipeline status: queued, fetching, ingesting, processing, imported, failed",
    )
    error_message: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    notes: Optional[str] = None
    max_builds_to_ingest: Optional[int] = None
    # Always detect languages; no toggle exposed

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        use_enum_values=True,
    )


class RepoDetailResponse(RepoResponse):
    metadata: Optional[Dict[str, Any]] = None


class RepoListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[RepoResponse]


class RepoSuggestion(BaseModel):
    full_name: str
    description: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    owner: Optional[str] = None
    html_url: Optional[str] = None
    github_repo_id: Optional[int] = None


class RepoSuggestionListResponse(BaseModel):
    items: List[RepoSuggestion]


class RepoSearchResponse(BaseModel):
    private_matches: List[RepoSuggestion]
    public_matches: List[RepoSuggestion]
