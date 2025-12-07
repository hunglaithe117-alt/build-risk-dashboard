"""GitHub integration DTOs"""

from app.entities.base import PyObjectIdStr
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class GithubInstallationResponse(BaseModel):
    id: PyObjectIdStr = Field(..., alias="_id")
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
