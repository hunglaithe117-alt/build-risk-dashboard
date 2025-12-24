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

    # ==========================================================================
    # Pipeline Batch Processing
    # ==========================================================================

    # --- Ingestion Phase (fetching builds, cloning repos, downloading logs) ---
    INGESTION_BUILDS_PER_PAGE: int = 40  # Builds fetched per API page
    INGESTION_WORKTREES_PER_CHUNK: int = 20  # Worktrees created per task
    INGESTION_LOGS_PER_CHUNK: int = 40  # Logs downloaded per task

    # --- Processing Phase (feature extraction) ---
    PROCESSING_BUILDS_PER_BATCH: int = 50  # Builds processed per enrichment batch

    # --- Validation Phase (CSV/repo validation) ---
    VALIDATION_CSV_CHUNK_SIZE: int = 1000  # Rows per CSV chunk
    VALIDATION_REPOS_PER_TASK: int = 20  # Repos per worker task
    VALIDATION_BUILDS_PER_TASK: int = 40  # Builds per worker task

    # --- Git/Log Constraints ---
    GIT_MAX_LOG_SIZE_MB: int = 10  # Skip logs larger than this
    GIT_COMMIT_REPLAY_MAX_DEPTH: int = 50  # Max depth for fork commit replay
    GIT_LOG_UNAVAILABLE_THRESHOLD: int = 10  # Stop after N consecutive unavailable

    # --- Scanning Phase (Trivy, SonarQube) ---
    SCAN_BUILDS_PER_QUERY: int = 200  # Builds fetched per paginated query
    SCAN_COMMITS_PER_BATCH: int = 20  # Commits dispatched per batch task
    SCAN_BATCH_DELAY_SECONDS: float = 0.2  # Delay between batch dispatches

    # --- Rate Limiting (GitHub API) ---
    GITHUB_API_RATE_PER_SECOND: float = 10.0  # Sustained request rate
    GITHUB_API_BURST_ALLOWANCE: int = 5  # Burst before throttling

    # --- CSV Dataset Limits ---
    CSV_MAX_FILE_SIZE_MB: int = 50  # Maximum CSV file size
    CSV_MAX_ROWS: int = 100000  # Maximum rows allowed
    CSV_MIN_ROWS: int = 1  # Minimum rows required
    CSV_BATCH_PROGRESS_INTERVAL: int = 100  # Rows between WebSocket updates
    CSV_DUPLICATE_WARN_THRESHOLD: float = 0.1  # Warn if >10% duplicates
    CSV_MISSING_WARN_THRESHOLD: float = 0.05  # Warn if >5% missing values

    # --- Hamilton Pipeline Caching ---
    HAMILTON_CACHE_ENABLED: bool = True  # Enable/disable DAG result caching
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

    # Trivy Security Scanner
    TRIVY_SERVER_URL: Optional[str] = None  # For client/server mode

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
