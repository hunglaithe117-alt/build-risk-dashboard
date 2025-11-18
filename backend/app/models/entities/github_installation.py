"""GitHub installation entity - tracks GitHub App installations"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class GithubInstallation(BaseModel):
    """GitHub App installation entity stored in MongoDB"""

    id: Optional[ObjectId] = Field(None, alias="_id")
    installation_id: str
    account_login: Optional[str] = None
    account_type: Optional[str] = None  # "User" or "Organization"
    installed_at: datetime
    revoked_at: Optional[datetime] = None
    uninstalled_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
