"""Repository DTOs"""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# Custom validator for MongoDB ObjectId
def validate_object_id(v: Any) -> str:
    """Validate and convert ObjectId to string."""
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


class RepoImportRequest(BaseModel):
    full_name: str = Field(..., description="Repository full name (e.g., owner/name)")
    provider: str = Field(default="github")
    user_id: Optional[str] = Field(
        default=None, description="Owner user id (defaults to admin)"
    )
    installation_id: Optional[str] = Field(
        default=None,
        description="GitHub App installation id (required for private repos, optional for public repos)",
    )


class RepoResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    user_id: Optional[PyObjectId] = None
    provider: str
    full_name: str
    default_branch: Optional[str] = None
    is_private: bool = False
    main_lang: Optional[str] = None
    github_repo_id: Optional[int] = None
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    installation_id: Optional[str] = None
    ci_provider: Literal["github_actions", "travis_ci"] = "github_actions"
    monitoring_enabled: bool = True
    sync_status: Literal["healthy", "error", "disabled"] = "healthy"
    webhook_status: Literal["active", "inactive"] = "inactive"
    ci_token_status: Literal["valid", "missing"] = "valid"
    tracked_branches: List[str] = Field(default_factory=list)
    total_builds_imported: int = 0
    last_sync_error: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class RepoDetailResponse(RepoResponse):
    metadata: Optional[Dict[str, Any]] = None


class RepoUpdateRequest(BaseModel):
    ci_provider: Optional[str] = None
    monitoring_enabled: Optional[bool] = None
    sync_status: Optional[Literal["healthy", "error", "disabled"]] = None
    tracked_branches: Optional[List[str]] = None
    webhook_status: Optional[Literal["active", "inactive"]] = None
    ci_token_status: Optional[Literal["valid", "missing"]] = None
    default_branch: Optional[str] = None
    notes: Optional[str] = None


class RepoSuggestion(BaseModel):
    full_name: str
    description: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    owner: Optional[str] = None
    installed: bool = False
    requires_installation: bool = False
    installation_id: Optional[str] = None
    html_url: Optional[str] = None


class RepoSuggestionListResponse(BaseModel):
    items: List[RepoSuggestion]
