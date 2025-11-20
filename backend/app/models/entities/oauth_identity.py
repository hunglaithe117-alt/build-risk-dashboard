from datetime import datetime
from bson import ObjectId

from .base import BaseEntity, PyObjectId


class OAuthIdentity(BaseEntity):
    user_id: PyObjectId
    provider: str
    external_user_id: str
    access_token: str
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    scopes: str | None = None
    account_login: str | None = None
    account_name: str | None = None
    account_avatar_url: str | None = None
    connected_at: datetime | None = None
