"""Repository for Notification entities."""

from typing import List

from bson import ObjectId

from app.entities.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Repository for Notification entities."""

    def __init__(self, db) -> None:
        super().__init__(db, "notifications", Notification)

    def find_by_user(
        self,
        user_id: ObjectId,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False,
        cursor_id: str | None = None,
    ) -> tuple[List[Notification], int]:
        """Find notifications for a user with pagination (offset or cursor)."""
        query = {"user_id": user_id}
        if unread_only:
            query["is_read"] = False

        if cursor_id:
            try:
                query["_id"] = {"$lt": ObjectId(cursor_id)}
            except Exception:
                pass  # Ignore invalid cursor

        # If using cursor, skip should be 0 (handled by caller usually), but we respect it if passed
        return self.paginate(query, sort=[("_id", -1)], skip=skip, limit=limit)

    def count_unread(self, user_id: ObjectId) -> int:
        """Count unread notifications for a user."""
        return self.count({"user_id": user_id, "is_read": False})

    def mark_as_read(self, notification_id: ObjectId) -> bool:
        """Mark a single notification as read."""
        result = self.collection.update_one(
            {"_id": notification_id},
            {"$set": {"is_read": True}},
        )
        return result.modified_count > 0

    def mark_all_as_read(self, user_id: ObjectId) -> int:
        """Mark all notifications as read for a user."""
        result = self.collection.update_many(
            {"user_id": user_id, "is_read": False},
            {"$set": {"is_read": True}},
        )
        return result.modified_count
