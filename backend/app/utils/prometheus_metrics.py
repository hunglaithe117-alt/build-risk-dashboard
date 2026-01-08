"""
Prometheus Metrics Integration

This module sets up Prometheus metrics for the FastAPI application.
Metrics are exposed at /api/metrics endpoint.
"""

import time
from typing import Callable

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info

# Custom metrics for business logic
BUILD_PREDICTIONS = Counter(
    "build_risk_predictions_total",
    "Total number of build risk predictions made",
    ["risk_level"],  # LOW, MEDIUM, HIGH
)

BUILDS_PROCESSED = Counter(
    "builds_processed_total",
    "Total number of builds processed through pipeline",
    ["status", "pipeline"],  # status: success/failed, pipeline: model/enrichment
)

FEATURE_EXTRACTION_DURATION = Histogram(
    "feature_extraction_duration_seconds",
    "Time spent extracting features from builds",
    ["repo_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

CELERY_QUEUE_DEPTH = Gauge(
    "celery_queue_depth",
    "Current number of tasks in each Celery queue",
    ["queue_name"],
)

ACTIVE_REPOSITORIES = Gauge(
    "active_repositories_total",
    "Total number of repositories being monitored",
    ["status"],  # queued, ingesting, processing, processed, failed
)

ACTIVE_DATASETS = Gauge(
    "active_datasets_total",
    "Total number of datasets being enriched",
    ["status"],
)


def setup_prometheus(app):
    """
    Initialize Prometheus instrumentation for the FastAPI app.

    This sets up:
    - Default HTTP request metrics (latency, count, size)
    - Custom business metrics
    - /api/metrics endpoint for Prometheus scraping
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/api/metrics", "/api/health", "/api/health/live"],
        inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
    )

    # Add default metrics
    instrumentator.add(
        metrics.request_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    instrumentator.add(
        metrics.response_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    instrumentator.add(
        metrics.latency(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )
    instrumentator.add(
        metrics.requests(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
        )
    )

    # Add custom info metric for app version
    instrumentator.add(build_info())

    # Instrument and expose
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/api/metrics", include_in_schema=True)

    return instrumentator


def build_info() -> Callable[[Info], None]:
    """Custom metric to expose build/version info."""
    from prometheus_client import Info as PrometheusInfo

    app_info_metric = PrometheusInfo(
        "build_risk_app", "Build Risk Dashboard application info"
    )
    app_info_metric.info(
        {
            "version": "1.0.0",
            "app_name": "build-risk-dashboard",
        }
    )

    def instrumentation(info: Info) -> None:
        pass  # Info is set once at startup

    return instrumentation


# Helper functions for recording business metrics
def record_prediction(risk_level: str):
    """Record a build risk prediction."""
    BUILD_PREDICTIONS.labels(risk_level=risk_level.upper()).inc()


def record_build_processed(status: str, pipeline: str):
    """Record a build that was processed."""
    BUILDS_PROCESSED.labels(status=status, pipeline=pipeline).inc()


def record_feature_extraction_time(repo_name: str, duration_seconds: float):
    """Record time spent on feature extraction."""
    FEATURE_EXTRACTION_DURATION.labels(repo_name=repo_name).observe(duration_seconds)


def update_queue_depth(queue_name: str, depth: int):
    """Update the current queue depth metric."""
    CELERY_QUEUE_DEPTH.labels(queue_name=queue_name).set(depth)


def update_repo_count(status: str, count: int):
    """Update active repository count by status."""
    ACTIVE_REPOSITORIES.labels(status=status).set(count)


def update_dataset_count(status: str, count: int):
    """Update active dataset count by status."""
    ACTIVE_DATASETS.labels(status=status).set(count)
