"""Available repository entity - caches repos available to user"""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class AvailableRepository(BaseModel):
    id: Optional[ObjectId] = Field(None, alias="_id")
    user_id: ObjectId  # The user who can see this repo
    full_name: str
    github_id: int
    private: bool
    html_url: str
    description: Optional[str] = None
    default_branch: str
    installation_id: Optional[str] = None  # If accessible via App
    imported: bool = False
    updated_at: datetime

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
