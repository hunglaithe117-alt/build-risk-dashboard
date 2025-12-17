"""DTOs for Admin Repository Access Control API."""

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr
from app.dtos.admin_user import AdminUserResponse


class RepoAccessSummary(BaseModel):
    """Summary of repository with access info."""

    id: PyObjectIdStr = Field(..., alias="_id")
    full_name: str
    visibility: str
    granted_user_count: int
    owner_id: str

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AdminRepoListResponse(BaseModel):
    """Response with list of all repos for admin."""

    items: List[RepoAccessSummary]
    total: int


class RepoAccessResponse(BaseModel):
    """Response with repository access information."""

    repo_id: str
    full_name: str
    visibility: str
    granted_users: List[AdminUserResponse]


class GrantAccessRequest(BaseModel):
    """Request to grant user access to a repository."""

    user_ids: List[str] = Field(..., description="List of user IDs to grant access")


class RevokeAccessRequest(BaseModel):
    """Request to revoke user access from a repository."""

    user_ids: List[str] = Field(..., description="List of user IDs to revoke access")


class VisibilityUpdateRequest(BaseModel):
    """Request to update repository visibility."""

    visibility: Literal["public", "private"] = Field(
        ..., description="New visibility setting"
    )
