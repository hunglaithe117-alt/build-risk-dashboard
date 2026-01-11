"""FastAPI application entry point."""

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_users,
    auth,
    build_sources,
    dashboard,
    features,
    health,
    integrations,
    logs,
    model_repos,
    monitoring,
    notifications,
    settings,
    sse,
    statistics,
    templates,
    tokens,
    training_scenarios,
    user_settings,
    users,
    webhook,
)
from app.middleware.exception_handlers import (
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.middleware.request_logging import RequestLoggingMiddleware

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
app.include_router(sse.router, prefix="/api", tags=["SSE"])
app.include_router(logs.router, prefix="/api", tags=["Logs"])
app.include_router(features.router, prefix="/api", tags=["Feature Definitions"])

app.include_router(
    training_scenarios.router,
    prefix="/api/training-scenarios",
    tags=["Training Scenarios"],
)
app.include_router(tokens.router, prefix="/api", tags=["GitHub Tokens"])
app.include_router(templates.router, prefix="/api", tags=["Templates"])
app.include_router(settings.router, prefix="/api", tags=["Settings"])
app.include_router(monitoring.router, prefix="/api", tags=["Monitoring"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
app.include_router(user_settings.router, prefix="/api", tags=["User Settings"])
app.include_router(statistics.router, prefix="/api", tags=["Statistics"])
app.include_router(build_sources.router, prefix="/api", tags=["Build Sources"])


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

    try:
        from app.database.mongo import get_database
        from app.services.settings_service import SettingsService

        db = get_database()
        settings_service = SettingsService(db)
        if settings_service.initialize_from_env():
            logger.info("Application settings initialized from ENV")
    except Exception as e:
        logger.warning(f"Failed to initialize settings: {e}")

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
        logger.info(
            f"Loaded {feature_count} feature definitions from Hamilton pipeline: {pipeline.get_active_features()}"
        )
    except Exception as e:
        logger.warning(f"Failed to load feature definitions: {e}")

    # Enable MongoDB logging for system log viewer UI
    try:
        from app.utils.mongo_log_handler import setup_mongodb_logging

        setup_mongodb_logging()
        logger.info("MongoDB logging handler enabled for WARNING+ logs")
    except Exception as e:
        logger.warning(f"Failed to setup MongoDB logging: {e}")

    # Setup Prometheus metrics
    try:
        from app.utils.prometheus_metrics import setup_prometheus

        setup_prometheus(app)
        logger.info("Prometheus metrics enabled at /api/metrics")
    except Exception as e:
        logger.warning(f"Failed to setup Prometheus metrics: {e}")
