"""Application settings API endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
)
from app.middleware.auth import get_current_user
from app.middleware.rbac import Permission, RequirePermission
from app.services.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/", response_model=ApplicationSettingsResponse)
def get_settings(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current application settings."""
    service = SettingsService(db)
    return service.get_settings()


@router.patch("/", response_model=ApplicationSettingsResponse)
def update_settings(
    request: ApplicationSettingsUpdateRequest,
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.ADMIN_FULL)),
):
    """Update application settings (Admin only)."""
    service = SettingsService(db)
    return service.update_settings(request)


@router.get("/available-metrics")
def get_available_metrics(
    current_user: dict = Depends(get_current_user),
):
    """
    Get all available metrics for all scan tools, grouped by category.

    Returns metrics from integrations layer, grouped by tool and category
    for frontend metric selection UI.
    """
    from app.integrations import get_all_metrics_grouped

    return get_all_metrics_grouped()
