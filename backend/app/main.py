"""FastAPI application entry point."""

import logging
import os

# Configure logging based on ENV environment variable
# ENV=dev: INFO level with detailed format (default)
# ENV=prod/staging: WARNING level, minimal logs
_env = os.getenv("ENV", "dev").lower()
_is_dev = _env == "dev"
_log_level = logging.INFO if _is_dev else logging.WARNING

logging.basicConfig(
    level=_log_level,
    format=(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        if _is_dev
        else "%(levelname)s | %(message)s"
    ),
    datefmt="%H:%M:%S",
)

# Enable request/exception loggers in dev mode only
if _is_dev:
    logging.getLogger("app.request").setLevel(logging.INFO)
    logging.getLogger("app.exception").setLevel(logging.INFO)

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

# ResponseWrapperMiddleware disabled - has issues with StreamingResponse
# from app.middleware.response_wrapper import ResponseWrapperMiddleware
from app.api import (
    admin_invitations,
    admin_users,
    auth,
    dashboard,
    dataset_validation,
    dataset_versions,
    datasets,
    export,
    features,
    health,
    integrations,
    logs,
    model_repos,
    monitoring,
    notifications,
    settings,
    templates,
    tokens,
    user_settings,
    users,
    webhook,
    websocket,
)
from app.middleware.exception_handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.request_logging import RequestLoggingMiddleware

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

# Register global exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)


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
app.include_router(dataset_validation.router, prefix="/api", tags=["Dataset Validation"])
app.include_router(dataset_versions.router, prefix="/api", tags=["Dataset Versions"])
app.include_router(templates.router, prefix="/api", tags=["Templates"])
app.include_router(settings.router, prefix="/api", tags=["Settings"])
app.include_router(monitoring.router, prefix="/api", tags=["Monitoring"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
app.include_router(user_settings.router, prefix="/api", tags=["User Settings"])

# Admin-only routes
app.include_router(admin_users.router, prefix="/api", tags=["Admin - Users"])
app.include_router(admin_invitations.router, prefix="/api", tags=["Admin - Invitations"])


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
        from app.database.ensure_indexes import ensure_indexes
        from app.database.mongo import get_database

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
        from app.database.mongo import get_database
        from app.tasks.pipeline.hamilton_runner import HamiltonPipeline

        db = get_database()
        pipeline = HamiltonPipeline(db)
        feature_count = len(pipeline.get_active_features())
        logger.info(f"Loaded {feature_count} feature definitions from Hamilton pipeline")
    except Exception as e:
        logger.warning(f"Failed to load feature definitions: {e}")
