"""Celery application bootstrap used by workers and FastAPI."""

from __future__ import annotations

from celery import Celery

from app.config import settings
from kombu import Exchange, Queue


celery_app = Celery(
    "buildguard",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.ingestion", "app.tasks.processing", "app.tasks.dataset"],
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
    ],
    broker_connection_retry_on_startup=True,
)


__all__ = ["celery_app"]
