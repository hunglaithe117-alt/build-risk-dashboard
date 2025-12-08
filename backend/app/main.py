"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    dashboard,
    health,
    integrations,
    auth,
    repos,
    users,
    webhook,
    websockets,
    logs,
    sonar,
    features,
    datasets,
    tokens,
    pipeline,
    websocket as enrichment_ws,
    export,
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

app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(integrations.router, prefix="/api", tags=["Integrations"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(repos.router, prefix="/api", tags=["Repositories"])
app.include_router(users.router, prefix="/api", tags=["Users"])
app.include_router(webhook.router, prefix="/api", tags=["Webhooks"])
app.include_router(websockets.router, prefix="/api", tags=["WebSockets"])
app.include_router(logs.router, prefix="/api", tags=["Logs"])
app.include_router(sonar.router, prefix="/api/sonar", tags=["SonarQube"])
app.include_router(features.router, prefix="/api", tags=["Feature Definitions"])
app.include_router(datasets.router, prefix="/api", tags=["Datasets"])
app.include_router(tokens.router, prefix="/api", tags=["GitHub Tokens"])
app.include_router(pipeline.router, prefix="/api", tags=["Pipeline"])
app.include_router(enrichment_ws.router, prefix="/api", tags=["Enrichment WebSocket"])
app.include_router(export.router, prefix="/api", tags=["Export"])


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
    from app.database.mongo import get_database
    from app.services.github.github_token_manager import seed_tokens_from_env

    # Seed GitHub tokens from environment variables into database
    try:
        db = get_database()
        added = seed_tokens_from_env(db)
        if added > 0:
            logger.info(
                f"Seeded {added} GitHub tokens from environment variables to MongoDB"
            )
    except Exception as e:
        logger.warning(f"Failed to seed GitHub tokens to MongoDB: {e}")

    # Seed tokens to Redis pool for distributed round-robin
    try:
        from app.services.github.redis_token_pool import get_redis_token_pool

        pool = get_redis_token_pool(db)
        synced = pool.sync_from_mongodb(db)
        if synced > 0:
            logger.info(f"Synced {synced} GitHub tokens to Redis pool")
        else:
            # Check if we already have tokens in Redis
            status = pool.get_pool_status()
            if status["total_tokens"] > 0:
                logger.info(f"Redis pool has {status['total_tokens']} tokens ready")
    except Exception as e:
        logger.warning(f"Failed to seed GitHub tokens to Redis: {e}")

    # Import pipeline to trigger @register_feature decorator execution
    try:
        import app.pipeline  # noqa: F401
        from app.pipeline.core.registry import feature_registry

        logger.info(
            f"Loaded {len(feature_registry.get_all_features())} feature definitions from code"
        )
    except Exception as e:
        logger.warning(f"Failed to load feature definitions: {e}")
