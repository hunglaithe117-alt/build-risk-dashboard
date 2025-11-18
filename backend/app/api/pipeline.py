"""Data pipeline status endpoints."""

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.models.schemas import PipelineStatusResponse, QueueHealthResponse
from app.services.data_pipeline import compute_pipeline_status
from app.services.queue_metrics import get_queue_health

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(db: Database = Depends(get_db)):
    """Return the latest preprocessing / normalization pipeline status."""
    return compute_pipeline_status(db)


@router.get("/queues", response_model=QueueHealthResponse)
def get_queue_health_status(db: Database = Depends(get_db)):
    """Return Celery/Rabbit-backed queue health metrics."""
    return get_queue_health(db)
