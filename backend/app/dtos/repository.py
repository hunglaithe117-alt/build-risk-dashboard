"""Repository DTOs"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.entities import TestFramework
from app.ci_providers.models import CIProvider
from app.entities.base import PyObjectIdStr


class RepoImportRequest(BaseModel):
    full_name: str = Field(..., description="Repository full name (e.g., owner/name)")
    installation_id: Optional[str] = Field(
        default=None,
        description="GitHub App installation id (required for private repos, optional for public repos)",
    )
    test_frameworks: List[str] = Field(default_factory=list)
    source_languages: List[str] = Field(
        ..., min_length=1, description="Source languages for the repository (required)"
    )
    ci_provider: CIProvider = Field(
        default=CIProvider.GITHUB_ACTIONS,
        description="CI/CD provider: github_actions, jenkins, circleci, travis_ci",
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
    provider: str
    full_name: str
    default_branch: Optional[str] = None
    is_private: bool = False
    main_lang: Optional[str] = None
    github_repo_id: Optional[int] = None
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    installation_id: Optional[str] = None
    ci_provider: CIProvider = CIProvider.GITHUB_ACTIONS
    test_frameworks: List[TestFramework] = Field(default_factory=list)
    source_languages: List[str] = Field(default_factory=list)
    total_builds_imported: int = 0
    import_status: Optional[str] = Field(
        default="imported",
        description="Import status: queued, importing, imported, failed",
    )
    last_sync_error: Optional[str] = None
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


class RepoUpdateRequest(BaseModel):
    ci_provider: Optional[CIProvider] = None
    test_frameworks: Optional[List[str]] = None
    source_languages: Optional[List[str]] = None
    default_branch: Optional[str] = None
    notes: Optional[str] = None
    max_builds: Optional[int] = Field(default=None, ge=1, le=1000)
    since_days: Optional[int] = Field(default=None, ge=1, le=365)


class RepoSuggestion(BaseModel):
    full_name: str
    description: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    owner: Optional[str] = None
    installation_id: Optional[str] = None
    html_url: Optional[str] = None


class RepoSuggestionListResponse(BaseModel):
    items: List[RepoSuggestion]


class RepoSearchResponse(BaseModel):
    private_matches: List[RepoSuggestion]
    public_matches: List[RepoSuggestion]
