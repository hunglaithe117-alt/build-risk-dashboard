"""Dashboard analytics endpoints."""

from bson import ObjectId
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import BuildSummary, DashboardSummaryResponse
from app.dtos.dashboard import (
    DashboardLayoutResponse,
    DashboardLayoutUpdateRequest,
    WidgetDefinition,
)
from app.middleware.auth import get_current_user
from app.services.dashboard_service import DashboardService
from app.services.model_build_service import ModelBuildService

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    db: Database = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """Return aggregated dashboard metrics derived from repository metadata."""
    dashboard_service = DashboardService(db)
    return dashboard_service.get_summary(current_user)


@router.get("/recent-builds", response_model=list[BuildSummary])
async def get_recent_builds(
    limit: int = 10,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return recent builds across repositories accessible to the user."""
    build_service = ModelBuildService(db)
    return build_service.get_recent_builds(limit, current_user)


@router.get("/layout", response_model=DashboardLayoutResponse)
def get_dashboard_layout(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current user's dashboard layout."""
    dashboard_service = DashboardService(db)
    user_id = ObjectId(current_user["_id"])
    return dashboard_service.get_layout(user_id)


@router.put("/layout", response_model=DashboardLayoutResponse)
def save_dashboard_layout(
    request: DashboardLayoutUpdateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Save current user's dashboard layout."""
    dashboard_service = DashboardService(db)
    user_id = ObjectId(current_user["_id"])
    return dashboard_service.save_layout(user_id, request.widgets)


@router.get("/available-widgets", response_model=list[WidgetDefinition])
def get_available_widgets(
    current_user: dict = Depends(get_current_user),
):
    """Get list of available widgets that can be added to the dashboard.

    Widgets are filtered based on user's role permissions.
    """
    from app.middleware.rbac import Permission, has_permission

    role = current_user.get("role", "user")

    # Common widgets (available to all users with appropriate permissions)
    common_widgets = [
        (
            WidgetDefinition(
                widget_id="total_builds",
                widget_type="stat",
                title="Total Builds",
                description="Total number of builds tracked",
                default_w=1,
                default_h=1,
            ),
            Permission.VIEW_BUILDS,
        ),
        (
            WidgetDefinition(
                widget_id="success_rate",
                widget_type="stat",
                title="Success Rate",
                description="Percentage of successful builds",
                default_w=1,
                default_h=1,
            ),
            Permission.VIEW_BUILDS,
        ),
        (
            WidgetDefinition(
                widget_id="avg_duration",
                widget_type="stat",
                title="Avg Duration",
                description="Average build duration",
                default_w=1,
                default_h=1,
            ),
            Permission.VIEW_BUILDS,
        ),
        (
            WidgetDefinition(
                widget_id="active_repos",
                widget_type="stat",
                title="Active Repos",
                description="Number of connected repositories",
                default_w=1,
                default_h=1,
            ),
            Permission.VIEW_REPOS,
        ),
        (
            WidgetDefinition(
                widget_id="repo_distribution",
                widget_type="table",
                title="Repository Distribution",
                description="Build count per repository",
                default_w=2,
                default_h=2,
            ),
            Permission.VIEW_REPOS,
        ),
        (
            WidgetDefinition(
                widget_id="recent_builds",
                widget_type="table",
                title="Recent Builds",
                description="Latest build runs with risk levels",
                default_w=2,
                default_h=2,
            ),
            Permission.VIEW_BUILDS,
        ),
        (
            WidgetDefinition(
                widget_id="risk_trend",
                widget_type="chart",
                title="Risk Trend",
                description="Build risk distribution over time",
                default_w=2,
                default_h=2,
            ),
            Permission.VIEW_BUILDS,
        ),
        (
            WidgetDefinition(
                widget_id="risk_distribution",
                widget_type="chart",
                title="Risk Distribution",
                description="Overall risk level breakdown (LOW/MED/HIGH)",
                default_w=2,
                default_h=2,
            ),
            Permission.VIEW_BUILDS,
        ),
        (
            WidgetDefinition(
                widget_id="high_risk_builds",
                widget_type="stat",
                title="High Risk Builds",
                description="Count of builds predicted as HIGH risk",
                default_w=1,
                default_h=1,
            ),
            Permission.VIEW_BUILDS,
        ),
    ]

    # Admin-only widgets (based on sidebar features)
    admin_widgets = [
        (
            WidgetDefinition(
                widget_id="dataset_enrichment_summary",
                widget_type="stat",
                title="Data Enrichments",
                description="Active projects and processing status",
                default_w=2,
                default_h=1,
            ),
            Permission.VIEW_DATASETS,
        ),
        (
            WidgetDefinition(
                widget_id="monitoring_summary",
                widget_type="stat",
                title="Monitoring Summary",
                description="System errors and alerts (24h)",
                default_w=2,
                default_h=1,
            ),
            Permission.ADMIN_FULL,
        ),
        (
            WidgetDefinition(
                widget_id="user_activity",
                widget_type="stat",
                title="User Activity",
                description="Total registered users",
                default_w=1,
                default_h=1,
            ),
            Permission.MANAGE_USERS,
        ),
    ]

    # User-only widgets (when user has no data, show onboarding)
    # Note: getting_started is dynamically shown based on user data, not permissions
    user_widgets = [
        (
            WidgetDefinition(
                widget_id="getting_started",
                widget_type="card",
                title="Getting Started",
                description="Quick start guide for new users",
                default_w=3,
                default_h=2,
            ),
            Permission.VIEW_OWN_DASHBOARD,
        ),
    ]

    # Return ALL widgets for all authenticated users
    # Role-based data filtering happens in the service layer, not widget visibility
    all_widgets = common_widgets + admin_widgets + user_widgets

    return [widget for widget, _ in all_widgets]
