"""User settings entity - represents user preferences."""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class UserSettings(BaseModel):
    """User settings entity stored in MongoDB.

    Simplified to only contain browser_notifications toggle.
    Email notifications are controlled at admin level via ApplicationSettings.
    """

    id: Optional[ObjectId] = Field(default=None, alias="_id")
    user_id: ObjectId
    browser_notifications: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        arbitrary_types_allowed = True
        populate_by_name = True

    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage."""
        return {
            "user_id": self.user_id,
            "browser_notifications": self.browser_notifications,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserSettings":
        """Create from MongoDB document."""
        return cls(
            id=data.get("_id"),
            user_id=data["user_id"],
            browser_notifications=data.get("browser_notifications", True),
            created_at=data.get("created_at", datetime.now()),
            updated_at=data.get("updated_at", datetime.now()),
        )
