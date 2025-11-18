"""Celery application bootstrap used by workers and FastAPI."""
from __future__ import annotations

from celery import Celery

from app.config import settings


celery_app = Celery(
    "buildguard",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND or settings.CELERY_BROKER_URL,
    include=[
        "app.tasks.repositories",
        "app.tasks.workflow",
        "app.tasks.builds",
        "app.tasks.logs",
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
    task_routes={
        "app.tasks.repositories.*": {"queue": "high"},
        "app.tasks.workflow.*": {"queue": "medium"},
        "app.tasks.builds.*": {"queue": "medium"},
        "app.tasks.logs.*": {"queue": "low"},
    },
)


__all__ = ["celery_app"]
