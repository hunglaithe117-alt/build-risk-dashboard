"""Repository for application settings."""

from typing import Optional

from pymongo.database import Database

from app.entities.settings import ApplicationSettings

from .base import BaseRepository


class SettingsRepository(BaseRepository[ApplicationSettings]):
    """Repository for application settings (single document)."""

    SETTINGS_ID = "app_settings_v1"

    def __init__(self, db: Database):
        super().__init__(db, "settings", ApplicationSettings)

    def get_settings(self) -> Optional[ApplicationSettings]:
        """Get the application settings document."""
        return self.find_one({"_id": self.SETTINGS_ID})

    def upsert_settings(self, settings: ApplicationSettings) -> ApplicationSettings:
        """Create or update application settings."""
        settings.id = self.SETTINGS_ID  # type: ignore
        existing = self.get_settings()

        if existing:
            # Update existing
            return self.update_one(
                self.SETTINGS_ID,
                settings.model_dump(by_alias=True, exclude_none=True),
            )
        else:
            # Insert new
            doc = settings.model_dump(by_alias=True, exclude_none=True)
            doc["_id"] = self.SETTINGS_ID
            self.collection.insert_one(doc)
            return settings
