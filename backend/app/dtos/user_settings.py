"""User Settings DTOs."""

from typing import Optional

from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    """Response DTO for user settings."""

    user_id: str
    browser_notifications: bool = Field(description="Enable browser push notifications")
    created_at: str
    updated_at: str


class UpdateUserSettingsRequest(BaseModel):
    """Request DTO to update user settings."""

    browser_notifications: Optional[bool] = Field(
        None, description="Enable/disable browser notifications"
    )
