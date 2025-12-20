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
from app.services.build_service import BuildService
from app.services.dashboard_service import DashboardService

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
    build_service = BuildService(db)
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
        WidgetDefinition(
            widget_id="risk_trend",
            widget_type="chart",
            title="Risk Trend",
            description="Build risk score over time (placeholder)",
            default_w=2,
            default_h=2,
        ),
        WidgetDefinition(
            widget_id="failure_heatmap",
            widget_type="chart",
            title="Failure Heatmap",
            description="Build failures by day/hour",
            default_w=2,
            default_h=2,
        ),
    ]
