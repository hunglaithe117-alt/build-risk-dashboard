"""Repository DTOs"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.entities.imported_repository import SourceLanguage
from app.models.entities.imported_repository import TestFramework
from app.models.entities.imported_repository import CIProvider
from app.models.entities.base import PyObjectIdStr


class RepoImportRequest(BaseModel):
    full_name: str = Field(..., description="Repository full name (e.g., owner/name)")
    provider: str = Field(default="github")
    installation_id: Optional[str] = Field(
        default=None,
        description="GitHub App installation id (required for private repos, optional for public repos)",
    )
    test_frameworks: Optional[List[str]] = Field(default=None)
    source_languages: Optional[List[str]] = Field(default=None)
    ci_provider: Optional[str] = Field(default=None)


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
    source_languages: List[SourceLanguage] = Field(default_factory=list)
    total_builds_imported: int = 0
    last_sync_error: Optional[str] = None
    notes: Optional[str] = None

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
    ci_provider: Optional[str] = None
    test_frameworks: Optional[List[str]] = None
    source_languages: Optional[List[str]] = None
    default_branch: Optional[str] = None
    notes: Optional[str] = None


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
