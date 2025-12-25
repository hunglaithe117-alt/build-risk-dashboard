"""Repository for user settings operations."""

from datetime import datetime
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.user_settings import UserSettings


class UserSettingsRepository:
    """Repository for user settings collection operations."""

    COLLECTION_NAME = "user_settings"

    def __init__(self, db: Database):
        self.db = db
        self.collection = db[self.COLLECTION_NAME]

    def find_by_user_id(self, user_id: ObjectId) -> Optional[UserSettings]:
        """Find settings by user ID."""
        document = self.collection.find_one({"user_id": user_id})
        if document:
            return UserSettings.from_dict(document)
        return None

    def get_or_create(self, user_id: ObjectId) -> UserSettings:
        """Get existing settings or create default for user."""
        existing_settings = self.find_by_user_id(user_id)
        if existing_settings:
            return existing_settings

        # Create default settings
        new_settings = UserSettings(user_id=user_id)
        result = self.collection.insert_one(new_settings.to_dict())
        new_settings.id = result.inserted_id
        return new_settings

    def update(
        self,
        user_id: ObjectId,
        browser_notifications: Optional[bool] = None,
    ) -> Optional[UserSettings]:
        """Update user settings."""
        update_fields: dict = {"updated_at": datetime.now()}

        if browser_notifications is not None:
            update_fields["browser_notifications"] = browser_notifications

        result = self.collection.find_one_and_update(
            {"user_id": user_id},
            {"$set": update_fields},
            return_document=True,
        )

        if result:
            return UserSettings.from_dict(result)
        return None

    def upsert(self, user_settings: UserSettings) -> UserSettings:
        """Insert or update user settings."""
        user_settings.updated_at = datetime.now()
        settings_dict = user_settings.to_dict()

        result = self.collection.find_one_and_update(
            {"user_id": user_settings.user_id},
            {"$set": settings_dict},
            upsert=True,
            return_document=True,
        )

        return UserSettings.from_dict(result)

    def delete_by_user_id(self, user_id: ObjectId) -> bool:
        """Delete settings for a user."""
        result = self.collection.delete_one({"user_id": user_id})
        return result.deleted_count > 0
