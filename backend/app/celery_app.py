"""Celery application bootstrap used by workers and FastAPI."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready
from kombu import Exchange, Queue

from app.config import settings

celery_app = Celery(
    "buildguard",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.model_ingestion",
        "app.tasks.model_processing",
        "app.tasks.dataset_validation",
        "app.tasks.enrichment_processing",
        "app.tasks.export",
        "app.tasks.sonar",
        "app.tasks.trivy",
    ],
)

celery_app.conf.update(
    task_default_queue=settings.CELERY_DEFAULT_QUEUE,
    task_default_exchange="buildguard",
    task_default_routing_key="pipeline.default",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    broker_heartbeat=settings.CELERY_BROKER_HEARTBEAT,
    task_queues=[
        # Default queue for unassigned tasks
        Queue(
            settings.CELERY_DEFAULT_QUEUE,
            Exchange("buildguard"),
            routing_key="pipeline.default",
        ),
        # Ingestion: clone repos, create worktrees, download logs, fetch builds
        Queue(
            "ingestion",
            Exchange("buildguard"),
            routing_key="pipeline.ingestion",
        ),
        # Processing: feature extraction, enrichment, export
        Queue(
            "processing",
            Exchange("buildguard"),
            routing_key="pipeline.processing",
        ),
        # Validation: dataset repo/build validation (can be long-running)
        Queue(
            "validation",
            Exchange("buildguard"),
            routing_key="pipeline.validation",
        ),
        # Sonar: CPU-intensive external tool, long-running
        Queue(
            "sonar_scan",
            Exchange("buildguard"),
            routing_key="pipeline.sonar_scan",
        ),
        # Trivy: Security scanning, external tool
        Queue(
            "trivy_scan",
            Exchange("buildguard"),
            routing_key="pipeline.trivy_scan",
        ),
        # Prediction: ML model inference, separate from processing
        Queue(
            "prediction",
            Exchange("buildguard"),
            routing_key="pipeline.prediction",
        ),
    ],
    broker_connection_retry_on_startup=True,
    # Celery Beat Schedule for periodic tasks
    beat_schedule={
        "cleanup-old-exports-weekly": {
            "task": "app.tasks.export.cleanup_old_exports",
            "schedule": crontab(hour=5, minute=0, day_of_week=0),  # Sunday 5 AM
            "args": (7,),  # Keep 7 days of exports
        },
    },
    timezone="UTC",
)


# Setup structured logging when worker starts


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Initialize structured logging when worker is ready."""
    from app.core.logging import setup_logging

    setup_logging()


__all__ = ["celery_app"]
