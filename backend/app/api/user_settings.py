"""User settings API endpoints."""

from bson import ObjectId
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    NotificationPreferencesDTO,
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)
from app.entities.user_settings import NotificationPreferences
from app.middleware.auth import get_current_user
from app.repositories.user_settings import UserSettingsRepository

router = APIRouter(prefix="/user-settings", tags=["User Settings"])


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/", response_model=UserSettingsResponse)
def get_user_settings(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current user's settings."""
    user_id = ObjectId(current_user["_id"])
    settings_repo = UserSettingsRepository(db)

    user_settings = settings_repo.get_or_create(user_id)

    return UserSettingsResponse(
        user_id=str(user_settings.user_id),
        notification_preferences=NotificationPreferencesDTO(
            email_on_version_complete=user_settings.notification_preferences.email_on_version_complete,
            email_on_scan_complete=user_settings.notification_preferences.email_on_scan_complete,
            email_on_version_failed=user_settings.notification_preferences.email_on_version_failed,
            browser_notifications=user_settings.notification_preferences.browser_notifications,
        ),
        timezone=user_settings.timezone,
        language=user_settings.language,
        created_at=user_settings.created_at.isoformat(),
        updated_at=user_settings.updated_at.isoformat(),
    )


@router.patch("/", response_model=UserSettingsResponse)
def update_user_settings(
    request: UpdateUserSettingsRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update current user's settings."""
    user_id = ObjectId(current_user["_id"])
    settings_repo = UserSettingsRepository(db)

    # Ensure settings exist
    existing_settings = settings_repo.get_or_create(user_id)

    # Convert DTO to entity if provided
    notification_prefs = None
    if request.notification_preferences:
        notification_prefs = NotificationPreferences(
            email_on_version_complete=request.notification_preferences.email_on_version_complete,
            email_on_scan_complete=request.notification_preferences.email_on_scan_complete,
            email_on_version_failed=request.notification_preferences.email_on_version_failed,
            browser_notifications=request.notification_preferences.browser_notifications,
        )

    updated_settings = settings_repo.update(
        user_id=user_id,
        notification_preferences=notification_prefs,
        timezone=request.timezone,
        language=request.language,
    )

    if not updated_settings:
        updated_settings = existing_settings

    return UserSettingsResponse(
        user_id=str(updated_settings.user_id),
        notification_preferences=NotificationPreferencesDTO(
            email_on_version_complete=updated_settings.notification_preferences.email_on_version_complete,
            email_on_scan_complete=updated_settings.notification_preferences.email_on_scan_complete,
            email_on_version_failed=updated_settings.notification_preferences.email_on_version_failed,
            browser_notifications=updated_settings.notification_preferences.browser_notifications,
        ),
        timezone=updated_settings.timezone,
        language=updated_settings.language,
        created_at=updated_settings.created_at.isoformat(),
        updated_at=updated_settings.updated_at.isoformat(),
    )
