"""Celery application bootstrap used by workers and FastAPI."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_ready
from kombu import Exchange, Queue

from app.config import settings

celery_app = Celery(
    "buildguard",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.model_ingestion",
        "app.tasks.model_processing",
        "app.tasks.source_validation",
        "app.tasks.training_ingestion",
        "app.tasks.training_processing",
        "app.tasks.training_scan_helpers",
        "app.tasks.export",
        "app.tasks.sonar",
        "app.tasks.trivy",
        "app.tasks.shared.ingestion_tasks",
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
        # Model Pipeline Queues
        Queue(
            "model_ingestion",
            Exchange("buildguard"),
            routing_key="pipeline.model_ingestion",
        ),
        Queue(
            "model_processing",
            Exchange("buildguard"),
            routing_key="pipeline.model_processing",
        ),
        Queue(
            "model_prediction",
            Exchange("buildguard"),
            routing_key="pipeline.model_prediction",
        ),
        # ML Scenario Pipeline Queues (replaced old Dataset Enrichment flow)
        Queue(
            "scenario_ingestion",
            Exchange("buildguard"),
            routing_key="pipeline.scenario_ingestion",
        ),
        Queue(
            "scenario_processing",
            Exchange("buildguard"),
            routing_key="pipeline.scenario_processing",
        ),
        Queue(
            "scenario_scanning",
            Exchange("buildguard"),
            routing_key="pipeline.scenario_scanning",
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
        # Shared / Generic Queues
        Queue(
            "ingestion",
            Exchange("buildguard"),
            routing_key="pipeline.ingestion",
        ),
        Queue(
            "processing",
            Exchange("buildguard"),
            routing_key="pipeline.processing",
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


# Reset MongoDB client after fork to ensure fork-safety
@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """Reset MongoDB client after fork to avoid fork-safety warnings."""
    from app.database import mongo

    # Reset the global client so each forked worker creates its own connection
    mongo._client = None


# Setup structured logging when worker starts


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Initialize structured logging when worker is ready."""
    from app.core.logging import setup_logging

    setup_logging()


__all__ = ["celery_app"]
