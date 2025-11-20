"""Dashboard analytics endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import DashboardSummaryResponse, BuildSummary
from app.middleware.auth import get_current_user
from app.services.dashboard_service import DashboardService
from app.services.build_service import BuildService

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
