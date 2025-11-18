"""Dashboard analytics endpoints."""
from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import DashboardSummaryResponse
from app.services.analytics_service import compute_dashboard_summary

router = APIRouter()


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(db: Database = Depends(get_db)):
    """Return aggregated dashboard metrics derived from build data."""
    return compute_dashboard_summary(db)
