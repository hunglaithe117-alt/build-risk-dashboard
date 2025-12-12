"""Celery application bootstrap used by workers and FastAPI."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings
from kombu import Exchange, Queue


celery_app = Celery(
    "buildguard",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.ingestion",
        "app.tasks.processing",
        "app.tasks.maintenance",
        "app.tasks.version_enrichment",
        "app.tasks.export",
        "app.tasks.sonar",
        "app.tasks.trivy",
        "app.tasks.dataset_validation",
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
        Queue(
            settings.CELERY_DEFAULT_QUEUE,
            Exchange("buildguard"),
            routing_key="pipeline.default",
        ),
        Queue(
            "import_repo", Exchange("buildguard"), routing_key="pipeline.import_repo"
        ),
        Queue(
            "collect_workflow_logs",
            Exchange("buildguard"),
            routing_key="pipeline.collect_workflow_logs",
        ),
        Queue(
            "data_processing",
            Exchange("buildguard"),
            routing_key="pipeline.data_processing",
        ),
        Queue(
            "export",
            Exchange("buildguard"),
            routing_key="pipeline.export",
        ),
        Queue(
            "sonar_scan",
            Exchange("buildguard"),
            routing_key="pipeline.sonar_scan",
        ),
        Queue(
            "trivy_scan",
            Exchange("buildguard"),
            routing_key="pipeline.trivy_scan",
        ),
        Queue(
            "enrichment",
            Exchange("buildguard"),
            routing_key="pipeline.enrichment",
        ),
    ],
    broker_connection_retry_on_startup=True,
    # Celery Beat Schedule for periodic tasks
    beat_schedule={
        "cleanup-pipeline-runs-daily": {
            "task": "app.tasks.maintenance.cleanup_pipeline_runs",
            "schedule": crontab(hour=3, minute=0),  # Daily at 3 AM
            "args": (30,),  # Keep 30 days of pipeline runs
        },
        "cleanup-failed-scans-weekly": {
            "task": "app.tasks.maintenance.cleanup_failed_scans",
            "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4 AM
            "args": (90,),  # Keep 90 days of resolved failed scans
        },
        "refresh-token-pool-hourly": {
            "task": "app.tasks.maintenance.refresh_token_pool",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        "cleanup-old-exports-weekly": {
            "task": "app.tasks.export.cleanup_old_exports",
            "schedule": crontab(hour=5, minute=0, day_of_week=0),  # Sunday 5 AM
            "args": (7,),  # Keep 7 days of exports
        },
    },
    timezone="UTC",
)


__all__ = ["celery_app"]
