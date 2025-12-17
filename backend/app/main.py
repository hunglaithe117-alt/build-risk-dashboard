"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    dashboard,
    health,
    integrations,
    auth,
    users,
    webhook,
    websocket,
    logs,
    features,
    datasets,
    tokens,
    export,
    dataset_validation,
    dataset_versions,
    templates,
    settings,
    monitoring,
    notifications,
    admin_users,
)
from app.middleware.request_logging import RequestLoggingMiddleware
from app.api import model_repos

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Build Risk Assessment API",
    description="API for assessing CI/CD build risks using Bayesian CNN",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trace middleware for request logging and correlation
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(integrations.router, prefix="/api", tags=["Integrations"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(model_repos.router, prefix="/api", tags=["Repositories"])
app.include_router(users.router, prefix="/api", tags=["Users"])
app.include_router(webhook.router, prefix="/api", tags=["Webhooks"])
app.include_router(websocket.router, prefix="/api", tags=["WebSocket"])
app.include_router(logs.router, prefix="/api", tags=["Logs"])
# sonar.router removed - merged into integrations.py
app.include_router(features.router, prefix="/api", tags=["Feature Definitions"])
app.include_router(datasets.router, prefix="/api", tags=["Datasets"])
app.include_router(tokens.router, prefix="/api", tags=["GitHub Tokens"])
app.include_router(export.router, prefix="/api", tags=["Export"])
app.include_router(
    dataset_validation.router, prefix="/api", tags=["Dataset Validation"]
)
app.include_router(dataset_versions.router, prefix="/api", tags=["Dataset Versions"])
app.include_router(templates.router, prefix="/api", tags=["Templates"])
app.include_router(settings.router, prefix="/api", tags=["Settings"])
app.include_router(monitoring.router, prefix="/api", tags=["Monitoring"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])

# Admin-only routes
app.include_router(admin_users.router, prefix="/api", tags=["Admin - Users"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Build Risk Assessment API",
        "version": "1.0.0",
        "docs": "/api/docs",
    }


@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    # Ensure MongoDB indexes exist
    try:
        from app.database.mongo import get_database
        from app.database.ensure_indexes import ensure_indexes

        db = get_database()
        ensure_indexes(db)
    except Exception as e:
        logger.warning(f"Failed to ensure database indexes: {e}")

    # Initialize GitHub token pool
    try:
        from app.services.github.redis_token_pool import get_redis_token_pool

        pool = get_redis_token_pool()
        status = pool.get_pool_status()
        if status["total_tokens"] > 0:
            logger.info(f"Redis pool has {status['total_tokens']} GitHub tokens ready")
        else:
            logger.warning("No GitHub tokens in Redis pool. Set GITHUB_TOKENS env var.")
    except Exception as e:
        logger.warning(f"Failed to initialize GitHub token pool: {e}")

    # Import pipeline to trigger feature module loading
    try:
        from app.tasks.pipeline.hamilton_runner import HamiltonPipeline
        from app.database.mongo import get_database

        db = get_database()
        pipeline = HamiltonPipeline(db)
        feature_count = len(pipeline.get_active_features())
        logger.info(
            f"Loaded {feature_count} feature definitions from Hamilton pipeline"
        )
    except Exception as e:
        logger.warning(f"Failed to load feature definitions: {e}")
