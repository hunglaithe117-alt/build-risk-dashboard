"""
Application configuration
"""

from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Build Risk Assessment"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Database (MongoDB)
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "buildguard"

    # GitHub
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_GRAPHQL_URL: str = "https://api.github.com/graphql"
    GITHUB_TOKENS: List[str] = []
    GITHUB_WEBHOOK_SECRET: Optional[str] = None
    GITHUB_APP_ID: Optional[str] = None
    GITHUB_APP_PRIVATE_KEY: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/integrations/github/callback"
    GITHUB_SCOPES: List[str] = ["read:user", "repo", "read:org", "workflow"]
    PIPELINE_PRIMARY_LANGUAGES: List[str] = ["python", "ruby"]
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # ML Model
    MODEL_PATH: str = "./app/ml/models/bayesian_cnn.pth"

    # Celery / RabbitMQ
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5672//"
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_DEFAULT_QUEUE: str = "pipeline.default"
    CELERY_TASK_SOFT_TIME_LIMIT: int = 600
    CELERY_TASK_TIME_LIMIT: int = 900
    CELERY_BROKER_HEARTBEAT: int = 30

    # Repository mirrors / schedulers
    REPO_MIRROR_ROOT: str = "./repo-mirrors"
    ARTIFACTS_ROOT: str = "./artifacts"
    WORKFLOW_POLL_INTERVAL_MINUTES: int = 15
    DEFAULT_REPO_OWNER_ID: int = 1

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
