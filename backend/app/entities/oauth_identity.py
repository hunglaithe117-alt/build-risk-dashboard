from __future__ import annotations

from datetime import datetime
from typing import Optional

from .base import BaseEntity, PyObjectId


class OAuthIdentity(BaseEntity):
    user_id: PyObjectId
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
