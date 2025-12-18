"""Repository for UserDashboardLayout entities."""

from typing import Optional

from bson import ObjectId

from app.entities.user_dashboard_layout import UserDashboardLayout
from app.repositories.base import BaseRepository


class UserDashboardLayoutRepository(BaseRepository[UserDashboardLayout]):
    """Repository for UserDashboardLayout entities."""

    def __init__(self, db) -> None:
        super().__init__(db, "user_dashboard_layouts", UserDashboardLayout)

    def find_by_user(self, user_id: ObjectId) -> Optional[UserDashboardLayout]:
        """Find dashboard layout for a user."""
        doc = self.collection.find_one({"user_id": user_id})
        return UserDashboardLayout(**doc) if doc else None

    def upsert_by_user(
        self,
        user_id: ObjectId,
        layout: UserDashboardLayout,
    ) -> UserDashboardLayout:
        """Upsert dashboard layout for a user."""
        from datetime import datetime

        doc_dict = layout.model_dump(by_alias=True, exclude_none=True)
        doc_dict["user_id"] = user_id
        doc_dict["updated_at"] = datetime.utcnow()
        # Remove created_at from $set to avoid conflict with $setOnInsert
        doc_dict.pop("created_at", None)

        self.collection.update_one(
            {"user_id": user_id},
            {"$set": doc_dict, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )

        return self.find_by_user(user_id)
