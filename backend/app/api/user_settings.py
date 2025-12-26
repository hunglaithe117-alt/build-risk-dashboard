"""User settings API endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.user_settings import (
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)
from app.middleware.auth import get_current_user
from app.repositories.user import UserRepository

router = APIRouter(prefix="/user-settings", tags=["User Settings"])


@router.get("/", response_model=UserSettingsResponse)
def get_user_settings(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current user's settings."""
    return UserSettingsResponse(
        user_id=str(current_user["_id"]),
        browser_notifications=current_user.get("browser_notifications", True),
        created_at=current_user.get("created_at").isoformat()
        if current_user.get("created_at")
        else "",
        updated_at=current_user.get("updated_at").isoformat()
        if current_user.get("updated_at")
        else "",
    )


@router.patch("/", response_model=UserSettingsResponse)
def update_user_settings(
    request: UpdateUserSettingsRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update current user's settings."""
    user_repo = UserRepository(db)
    user_id = str(current_user["_id"])

    updated_user = user_repo.update_settings(
        user_id=user_id,
        browser_notifications=request.browser_notifications,
    )

    if not updated_user:
        # Return current state if update failed
        return UserSettingsResponse(
            user_id=user_id,
            browser_notifications=current_user.get("browser_notifications", True),
            created_at=current_user.get("created_at").isoformat()
            if current_user.get("created_at")
            else "",
            updated_at=current_user.get("updated_at").isoformat()
            if current_user.get("updated_at")
            else "",
        )

    return UserSettingsResponse(
        user_id=str(updated_user.id),
        browser_notifications=updated_user.browser_notifications,
        created_at=updated_user.created_at.isoformat() if updated_user.created_at else "",
        updated_at=updated_user.updated_at.isoformat() if updated_user.updated_at else "",
    )
