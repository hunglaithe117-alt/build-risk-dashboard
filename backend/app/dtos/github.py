"""GitHub integration DTOs"""

from datetime import datetime
from typing import Annotated, Any, List, Literal, Optional

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


class GithubRepositoryStatus(BaseModel):
    name: str
    lastSync: Optional[datetime] = None
    buildCount: int
    status: str


class GithubAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class GithubOAuthInitRequest(BaseModel):
    redirect_path: Optional[str] = None


class GithubImportRequest(BaseModel):
    repository: str
    branch: str = Field(..., description="Default branch to scan (e.g., main)")
    initiated_by: Optional[str] = Field(
        default="admin", description="User requesting the import"
    )
    user_id: Optional[str] = Field(
        default=None, description="Owner user id (defaults to admin)"
    )


class GithubImportJobResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    repository: str
    branch: str
    user_id: Optional[PyObjectId] = None
    installation_id: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed", "waiting_webhook"]
    progress: int = Field(..., ge=0, le=100)
    builds_imported: int
    commits_analyzed: int
    tests_collected: int
    initiated_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class GithubInstallationResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    installation_id: str
    account_login: Optional[str] = None
    account_type: Optional[str] = None  # "User" or "Organization"
    installed_at: datetime
    revoked_at: Optional[datetime] = None
    uninstalled_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class GithubInstallationListResponse(BaseModel):
    installations: List[GithubInstallationResponse]
