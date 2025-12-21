from typing import List, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Build Risk Assessment"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENV: str = "dev"  # Environment: "dev", "staging", "prod"

    # Database (MongoDB)
    MONGODB_URI: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "buildguard"

    # GitHub
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_GRAPHQL_URL: str = "https://api.github.com/graphql"
    GITHUB_TOKENS: List[str] = []
    GITHUB_WEBHOOK_SECRET: Optional[str] = None
    GITHUB_APP_ID: Optional[str] = None
    GITHUB_APP_PRIVATE_KEY: str
    GITHUB_INSTALLATION_ID: str
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

    # RBAC / Organization Access
    GITHUB_ORGANIZATION: Optional[str] = None  # GitHub org name for membership check
    REQUIRE_ORG_MEMBERSHIP: bool = True

    # Google OAuth (for guest login via Gmail)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

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

    # Pipeline Configurations
    ENRICHMENT_BATCH_SIZE: int = 50  # Builds per enrichment batch
    ENRICHMENT_MAX_RETRIES: int = 3  # Auto-retry count for enrichment
    MAX_LOG_SIZE_MB: int = 10  # Skip logs larger than this size
    DOWNLOAD_LOGS_BATCH_SIZE: int = 100  # Number of logs to download per batch
    PROCESSING_BATCH_SIZE: int = 50
    WORKTREE_BATCH_SIZE: int = 50  # Worktrees to create per chunk
    API_RATE_LIMIT_PER_SECOND: float = 10.0  # GitHub API calls per second
    COMMIT_REPLAY_MAX_DEPTH: int = 100  # Max depth to traverse for commit replay
    LOG_UNAVAILABLE_THRESHOLD: int = 10  # Stop after N consecutive unavailable logs

    # Ingestion Configuration
    INGESTION_MAX_RETRIES: int = 2  # Retries per ingestion task
    INGESTION_RETRY_DELAY: int = 30  # Seconds between retries

    # CSV Dataset Validation
    CSV_MAX_FILE_SIZE_MB: int = 50  # Maximum CSV file size in MB
    CSV_MAX_ROWS: int = 100000  # Maximum rows allowed in CSV
    CSV_BATCH_SIZE: int = 500  # Rows per batch for validation processing
    CSV_BATCH_PROGRESS_INTERVAL: int = 100  # Rows between WebSocket progress updates
    CSV_DUPLICATE_WARN_THRESHOLD: float = 0.1  # Warn if >10% duplicates
    CSV_MISSING_WARN_THRESHOLD: float = 0.05  # Warn if >5% missing values
    CSV_MIN_ROWS: int = 1  # Minimum rows required

    # Distributed Validation Processing
    CSV_CHUNK_SIZE: int = 10000  # Rows per CSV chunk for chunked reading
    REPO_CHUNK_SIZE: int = 20  # Repos per worker task
    BUILD_CHUNK_SIZE: int = 500  # Builds per worker task
    VALIDATION_RATE_LIMIT: str = "10/s"  # Celery rate limit for API calls

    # Hamilton Pipeline Caching
    HAMILTON_CACHE_ENABLED: bool = True  # Enable/disable DAG result caching
    HAMILTON_CACHE_DIR: str = "../repo-data/hamilton_cache"  # Directory for cache files
    HAMILTON_CACHE_TYPE: str = "file"  # "file" (persistent) or "memory" (dev only)

    DATA_DIR: str = "../repo-data/data"

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

    # Gmail API (OAuth2) Notifications
    GMAIL_TOKEN_JSON: Optional[str] = None  # Paste gmail token JSON content

    def model_post_init(self, __context):
        """Post-initialization to check for Gmail API capability."""
        super().model_post_init(__context)

        if self.GMAIL_TOKEN_JSON:
            print("✓ Gmail API configured (GMAIL_TOKEN_JSON found).")
        else:
            print("! Gmail API not configured (GMAIL_TOKEN_JSON missing).")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
