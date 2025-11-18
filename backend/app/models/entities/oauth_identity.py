"""OAuth identity entity - represents OAuth provider linkage"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class OAuthIdentity(BaseModel):
    """OAuth identity entity stored in MongoDB"""

    id: Optional[ObjectId] = Field(None, alias="_id")
    user_id: ObjectId
    provider: str
    external_user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: Optional[str] = None
    account_login: Optional[str] = None
    account_name: Optional[str] = None
    account_avatar_url: Optional[str] = None
    connected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
