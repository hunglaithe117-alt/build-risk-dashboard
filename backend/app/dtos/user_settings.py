"""User Settings DTOs."""

from typing import Optional

from pydantic import BaseModel


class NotificationPreferencesDTO(BaseModel):
    """DTO for notification preferences."""

    email_on_version_complete: bool = True
    email_on_scan_complete: bool = True
    email_on_version_failed: bool = True
    browser_notifications: bool = True


class UserSettingsResponse(BaseModel):
    """Response DTO for user settings."""

    user_id: str
    notification_preferences: NotificationPreferencesDTO
    timezone: str
    language: str
    created_at: str
    updated_at: str


class UpdateUserSettingsRequest(BaseModel):
    """Request DTO to update user settings."""

    notification_preferences: Optional[NotificationPreferencesDTO] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
