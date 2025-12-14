from pydantic_settings import BaseSettings
from typing import List, Optional


class Settings(BaseSettings):

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
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/auth/github/callback"
    GITHUB_SCOPES: List[str] = [
        "read:user",
        "user:email",
        "repo",
        "read:org",
        "workflow",
    ]
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # GitLab CI
    GITLAB_TOKEN: Optional[str] = None
    GITLAB_BASE_URL: str = "https://gitlab.com/api/v4"

    # Jenkins
    JENKINS_URL: Optional[str] = None
    JENKINS_USERNAME: Optional[str] = None
    JENKINS_TOKEN: Optional[str] = None

    # CircleCI
    CIRCLECI_TOKEN: Optional[str] = None
    CIRCLECI_BASE_URL: str = "https://circleci.com/api/v2"

    # Travis CI
    TRAVIS_TOKEN: Optional[str] = None
    TRAVIS_BASE_URL: str = "https://api.travis-ci.com"

    # ML Model
    # MODEL_PATH: str = "./app/ml/models/bayesian_cnn.pth"

    # Celery / RabbitMQ
    CELERY_BROKER_URL: str = "amqp://myuser:mypass@localhost:5672//"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_DEFAULT_QUEUE: str = "pipeline.default"
    CELERY_TASK_SOFT_TIME_LIMIT: int = 600
    CELERY_TASK_TIME_LIMIT: int = 900
    CELERY_BROKER_HEARTBEAT: int = 30

    # Dataset Enrichment Pipeline
    VALIDATION_BATCH_SIZE: int = 50  # Builds per validation batch
    ENRICHMENT_BATCH_SIZE: int = 50  # Builds per enrichment batch
    VALIDATION_MAX_RETRIES: int = 3  # Auto-retry count for validation
    ENRICHMENT_MAX_RETRIES: int = 3  # Auto-retry count for enrichment

    # Repository mirrors / schedulers
    REPO_MIRROR_ROOT: str = "../repo-data/repo-mirrors"
    ARTIFACTS_ROOT: str = "../repo-data/artifacts"
    DATA_DIR: str = "../repo-data/data"
    WORKFLOW_POLL_INTERVAL_MINUTES: int = 15

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # SonarQube
    SONAR_HOST_URL: str = "http://localhost:9000"
    SONAR_TOKEN: str = ""
    SONAR_DEFAULT_PROJECT_KEY: str = "build-risk-ui"
    SONAR_WEBHOOK_SECRET: str = "change-me-change-me"
    SONAR_WEBHOOK_PUBLIC_URL: str = "http://localhost:8000/api/sonar/webhook"

    # Trivy (security scanner)
    TRIVY_ENABLED: bool = False
    TRIVY_SEVERITY: str = "CRITICAL,HIGH,MEDIUM"
    TRIVY_TIMEOUT: int = 300  # Seconds
    TRIVY_SKIP_DIRS: str = "node_modules,vendor,.git"
    TRIVY_ASYNC_THRESHOLD: int = 1000

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
