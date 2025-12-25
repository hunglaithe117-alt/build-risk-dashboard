"""Notification DTOs."""

from typing import Optional

from pydantic import BaseModel

from app.entities.notification import NotificationType


class NotificationResponse(BaseModel):
    """Response DTO for a single notification."""

    id: str
    type: str
    title: str
    message: str
    is_read: bool
    link: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: str


class NotificationListResponse(BaseModel):
    """Response DTO for notification list."""

    items: list[NotificationResponse]
    total: int
    unread_count: int
    next_cursor: Optional[str] = None


class UnreadCountResponse(BaseModel):
    """Response DTO for unread count."""

    count: int


class MarkReadResponse(BaseModel):
    """Response DTO for mark as read operations."""

    success: bool
    marked_count: int = 1


class CreateNotificationRequest(BaseModel):
    """Request DTO to create a notification (for testing/admin)."""

    type: NotificationType
    title: str
    message: str
    link: Optional[str] = None
    metadata: Optional[dict] = None
