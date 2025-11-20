"""Available repository entity - caches repos available to user"""

from bson import ObjectId

from .base import BaseEntity, PyObjectId


class AvailableRepository(BaseEntity):
    user_id: PyObjectId  # The user who can see this repo
    full_name: str
    github_id: int
    private: bool
    html_url: str
    description: str | None = None
    default_branch: str
    installation_id: str | None = None  # If accessible via App
    imported: bool = False
