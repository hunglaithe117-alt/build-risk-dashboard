"""Application settings API endpoints."""

from fastapi import APIRouter, Depends, status
from pymongo.database import Database
from bson import ObjectId

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.dtos.settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
    DashboardLayoutResponse,
    DashboardLayoutUpdateRequest,
    WidgetConfigDto,
    WidgetDefinition,
)
from app.services.settings_service import SettingsService
from app.repositories.user_dashboard_layout import UserDashboardLayoutRepository
from app.entities.user_dashboard_layout import (
    UserDashboardLayout,
    WidgetConfig,
    DEFAULT_WIDGETS,
)


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


@router.get("/dashboard-layout", response_model=DashboardLayoutResponse)
def get_dashboard_layout(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current user's dashboard layout."""
    repo = UserDashboardLayoutRepository(db)
    user_id = ObjectId(current_user["_id"])
    layout = repo.find_by_user(user_id)

    def to_dto(w: WidgetConfig) -> WidgetConfigDto:
        return WidgetConfigDto(
            widget_id=w.widget_id,
            widget_type=w.widget_type,
            title=w.title,
            enabled=w.enabled,
            x=w.x,
            y=w.y,
            w=w.w,
            h=w.h,
        )

    if not layout:
        # Return default layout for new users
        return DashboardLayoutResponse(widgets=[to_dto(w) for w in DEFAULT_WIDGETS])

    return DashboardLayoutResponse(widgets=[to_dto(w) for w in layout.widgets])


@router.put("/dashboard-layout", response_model=DashboardLayoutResponse)
def save_dashboard_layout(
    request: DashboardLayoutUpdateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Save current user's dashboard layout."""
    repo = UserDashboardLayoutRepository(db)
    user_id = ObjectId(current_user["_id"])

    # Convert request widgets to entity widgets
    widget_configs = [
        WidgetConfig(
            widget_id=w.widget_id,
            widget_type=w.widget_type,
            title=w.title,
            enabled=w.enabled,
            x=w.x,
            y=w.y,
            w=w.w,
            h=w.h,
        )
        for w in request.widgets
    ]

    layout = UserDashboardLayout(user_id=user_id, widgets=widget_configs)
    saved = repo.upsert_by_user(user_id, layout)

    return DashboardLayoutResponse(widgets=saved.widgets)


@router.get("/available-widgets", response_model=list[WidgetDefinition])
def get_available_widgets(
    current_user: dict = Depends(get_current_user),
):
    """Get list of available widgets that can be added to the dashboard."""
    return [
        WidgetDefinition(
            widget_id="total_builds",
            widget_type="stat",
            title="Total Builds",
            description="Total number of builds tracked",
            default_w=1,
            default_h=1,
        ),
        WidgetDefinition(
            widget_id="success_rate",
            widget_type="stat",
            title="Success Rate",
            description="Percentage of successful builds",
            default_w=1,
            default_h=1,
        ),
        WidgetDefinition(
            widget_id="avg_duration",
            widget_type="stat",
            title="Avg Duration",
            description="Average build duration",
            default_w=1,
            default_h=1,
        ),
        WidgetDefinition(
            widget_id="active_repos",
            widget_type="stat",
            title="Active Repos",
            description="Number of connected repositories",
            default_w=1,
            default_h=1,
        ),
        WidgetDefinition(
            widget_id="repo_distribution",
            widget_type="table",
            title="Repository Distribution",
            description="Build count per repository",
            default_w=2,
            default_h=2,
        ),
        WidgetDefinition(
            widget_id="recent_builds",
            widget_type="table",
            title="Recent Builds",
            description="Latest build runs",
            default_w=2,
            default_h=2,
        ),
        WidgetDefinition(
            widget_id="active_tasks",
            widget_type="table",
            title="Active Pipeline Tasks",
            description="Currently running tasks",
            default_w=2,
            default_h=2,
        ),
        WidgetDefinition(
            widget_id="dataset_summary",
            widget_type="stat",
            title="Datasets",
            description="Total datasets count",
            default_w=1,
            default_h=1,
        ),
    ]
