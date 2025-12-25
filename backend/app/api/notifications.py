"""Notification API endpoints."""

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    CreateNotificationRequest,
    MarkReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.entities.notification import Notification
from app.middleware.auth import get_current_user
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ============================================================================
# Helper Functions
# ============================================================================


def _to_response(notification: Notification) -> NotificationResponse:
    """Convert entity to response DTO."""
    return NotificationResponse(
        id=str(notification.id),
        type=notification.type.value,
        title=notification.title,
        message=notification.message,
        is_read=notification.is_read,
        link=notification.link,
        metadata=notification.metadata,
        created_at=notification.created_at.isoformat(),
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/", response_model=NotificationListResponse)
def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    cursor: str | None = Query(None),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List notifications for the current user."""
    notification_service = NotificationService(db)
    user_id = ObjectId(current_user["_id"])

    items, total, unread_count, next_cursor = notification_service.list_notifications(
        user_id, skip=skip, limit=limit, unread_only=unread_only, cursor=cursor
    )

    return NotificationListResponse(
        items=[_to_response(n) for n in items],
        total=total,
        unread_count=unread_count,
        next_cursor=next_cursor,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
def get_unread_count(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the count of unread notifications."""
    notification_service = NotificationService(db)
    user_id = ObjectId(current_user["_id"])
    count = notification_service.get_unread_count(user_id)
    return UnreadCountResponse(count=count)


@router.put("/{notification_id}/read", response_model=MarkReadResponse)
def mark_as_read(
    notification_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark a single notification as read."""
    notification_service = NotificationService(db)
    user_id = ObjectId(current_user["_id"])

    success = notification_service.mark_as_read(user_id, notification_id)
    return MarkReadResponse(success=success, marked_count=1 if success else 0)


@router.put("/read-all", response_model=MarkReadResponse)
def mark_all_as_read(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark all notifications as read for the current user."""
    notification_service = NotificationService(db)
    user_id = ObjectId(current_user["_id"])
    count = notification_service.mark_all_as_read(user_id)
    return MarkReadResponse(success=True, marked_count=count)


@router.post("/", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(
    request: CreateNotificationRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a notification (for testing/admin purposes)."""
    notification_service = NotificationService(db)
    user_id = ObjectId(current_user["_id"])

    created = notification_service.create_notification(
        user_id=user_id,
        notification_type=request.type,
        title=request.title,
        message=request.message,
        link=request.link,
        metadata=request.metadata,
    )
    return _to_response(created)
