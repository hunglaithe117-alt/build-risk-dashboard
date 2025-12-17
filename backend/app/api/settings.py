"""Application settings API endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.dtos.settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
)
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
    current_user: dict = Depends(get_current_user),
):
    """Update application settings."""
    service = SettingsService(db)
    return service.update_settings(request)


@router.get("/available-metrics")
def get_available_metrics(
    current_user: dict = Depends(get_current_user),
):
    """Get all available metrics for each tool, grouped by category."""
    from app.integrations.tools.sonarqube import SONARQUBE_METRICS
    from app.integrations.tools.trivy import TRIVY_METRICS

    def format_metrics(metrics_list):
        """Group metrics by category."""
        grouped = {}
        for m in metrics_list:
            category = m.category.value
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(
                {
                    "key": m.key,
                    "display_name": m.display_name,
                    "description": m.description,
                    "data_type": m.data_type.value,
                }
            )
        return grouped

    return {
        "sonarqube": {
            "metrics": format_metrics(SONARQUBE_METRICS),
            "all_keys": [m.key for m in SONARQUBE_METRICS],
        },
        "trivy": {
            "metrics": format_metrics(TRIVY_METRICS),
            "all_keys": [m.key for m in TRIVY_METRICS],
        },
    }
