"""User settings entity - represents user preferences and notification settings."""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class NotificationPreferences(BaseModel):
    """User notification preferences."""

    email_on_version_complete: bool = True
    email_on_scan_complete: bool = True
    email_on_version_failed: bool = True
    browser_notifications: bool = True


class UserSettings(BaseModel):
    """User settings entity stored in MongoDB."""

    id: Optional[ObjectId] = Field(default=None, alias="_id")
    user_id: ObjectId
    notification_preferences: NotificationPreferences = Field(
        default_factory=NotificationPreferences
    )
    timezone: str = "UTC"
    language: str = "vi"
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        arbitrary_types_allowed = True
        populate_by_name = True

    def to_dict(self) -> dict:
        """Convert to dictionary for MongoDB storage."""
        return {
            "user_id": self.user_id,
            "notification_preferences": self.notification_preferences.model_dump(),
            "timezone": self.timezone,
            "language": self.language,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserSettings":
        """Create from MongoDB document."""
        notification_prefs = data.get("notification_preferences", {})
        return cls(
            id=data.get("_id"),
            user_id=data["user_id"],
            notification_preferences=NotificationPreferences(**notification_prefs),
            timezone=data.get("timezone", "UTC"),
            language=data.get("language", "vi"),
            created_at=data.get("created_at", datetime.now()),
            updated_at=data.get("updated_at", datetime.now()),
        )
