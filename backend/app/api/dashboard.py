"""Dashboard analytics endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database
from bson import ObjectId

from app.database.mongo import get_db
from app.dtos import DashboardSummaryResponse, BuildSummary
from app.dtos.dashboard import (
    DashboardLayoutResponse,
    DashboardLayoutUpdateRequest,
    WidgetConfigDto,
    WidgetDefinition,
)
from app.middleware.auth import get_current_user
from app.services.dashboard_service import DashboardService
from app.services.build_service import BuildService
from app.repositories.user_dashboard_layout import UserDashboardLayoutRepository
from app.entities.user_dashboard_layout import (
    UserDashboardLayout,
    WidgetConfig,
    DEFAULT_WIDGETS,
)

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    db: Database = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """Return aggregated dashboard metrics derived from repository metadata."""
    service = DashboardService(db)
    return service.get_summary()


@router.get("/recent-builds", response_model=list[BuildSummary])
async def get_recent_builds(
    limit: int = 10,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return recent builds across all repositories."""
    service = BuildService(db)
    return service.get_recent_builds(limit)


@router.get("/layout", response_model=DashboardLayoutResponse)
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


@router.put("/layout", response_model=DashboardLayoutResponse)
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
