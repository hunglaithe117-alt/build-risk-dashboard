"""User settings API endpoints."""

from bson import ObjectId
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.user_settings import (
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)
from app.middleware.auth import get_current_user
from app.repositories.user_settings import UserSettingsRepository

router = APIRouter(prefix="/user-settings", tags=["User Settings"])


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
        browser_notifications=user_settings.browser_notifications,
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

    updated_settings = settings_repo.update(
        user_id=user_id,
        browser_notifications=request.browser_notifications,
    )

    if not updated_settings:
        updated_settings = existing_settings

    return UserSettingsResponse(
        user_id=str(updated_settings.user_id),
        browser_notifications=updated_settings.browser_notifications,
        created_at=updated_settings.created_at.isoformat(),
        updated_at=updated_settings.updated_at.isoformat(),
    )
