# Build Risk Dashboard

A comprehensive CI/CD risk assessment platform with SonarQube code quality integration and feature extraction pipeline.

## Prerequisites

- **Docker & Docker Compose**: For running infrastructure services (MongoDB, RabbitMQ, Redis)
- **Python 3.11+**: For the backend. Requires `uv` for package management
- **Node.js 18+**: For the frontend
- **GitHub App**: Required for authentication and webhooks
- **SonarQube Server** (Optional): For code quality scanning. Can use local instance or cloud service

## Project Structure

```
├── backend/           # FastAPI application, Celery workers, and domain logic
│   ├── app/
│   │   ├── api/              # REST API endpoints
│   │   ├── entities/         # Database entities (MongoDB documents)
│   │   ├── repositories/     # Data access layer
│   │   ├── services/         # Business logic
│   │   ├── tasks/            # Celery async tasks
│   │   │   └── pipeline/     # Hamilton feature DAG pipeline
│   │   ├── celery_app.py     # Celery configuration
│   │   ├── config.py         # Application settings
│   │   └── main.py           # FastAPI app entry point
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/          # Next.js web application
├── docker-compose.yml # Infrastructure definitions
└── README.md
```

## Local Development Setup

### 1. Infrastructure

Start the required databases and message brokers:

```bash
docker-compose up -d mongo rabbitmq redis
```

This will start:
- **MongoDB** (port 27017) - Primary database
- **RabbitMQ** (ports 5672, 15672) - Celery message broker
- **Redis** (port 6379) - Cache and Celery result backend

**RabbitMQ Management Console**: http://localhost:15672 (default: `myuser` / `mypass`)

### 2. Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a `.env` file from example:
   ```bash
   cp .env.example .env
   ```

3. Update the `.env` file with your configuration:
   ```env
   # Required: GitHub App Configuration
   GITHUB_APP_ID=your_app_id
   GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY----- ... "
   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   GITHUB_WEBHOOK_SECRET=your_webhook_secret
   
   # Required: Security
   SECRET_KEY=your_secret_key
   
   # Optional: SonarQube
   SONAR_TOKEN=your_sonarqube_token
   ```

4. Install dependencies:
   ```bash
   # Using uv (required)
   uv sync
   ```

5. Run the API server:
   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/api/docs

6. Run Celery worker (in a separate terminal):
   ```bash
   cd backend
   uv run celery -A app.celery_app worker --loglevel=info
   ```

   **Celery Queues:**
   | Queue | Purpose |
   |-------|---------|
   | `pipeline.default` | Default queue for unassigned tasks |
   | `ingestion` | Clone repos, create worktrees, download logs, fetch builds |
   | `processing` | Feature extraction, validation, enrichment, export |
   | `sonar_scan` | SonarQube code analysis (long-running) |
   | `trivy_scan` | Security vulnerability scanning |

7. Run Celery Beat scheduler (optional, for periodic tasks):
   ```bash
   cd backend
   uv run celery -A app.celery_app beat --loglevel=info
   ```

### 3. Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   # or
   yarn install
   ```

3. Create a `.env.local` file (optional, defaults work for local dev):
   ```env
   NEXT_PUBLIC_API_URL=http://localhost:8000/api
   ```

4. Run the development server:
   ```bash
   npm run dev
   ```

5. Open http://localhost:3000 in your browser

### 4. SonarQube & Trivy Setup (Optional)

Both services are included in the docker-compose.yml:

```bash
# Start all infrastructure including SonarQube and Trivy
docker-compose up -d
```

This starts:
- **SonarQube**: http://localhost:9000 (default: `admin` / `admin`)
- **Trivy Server**: Port 4954 (used internally by backend)

**First-time SonarQube Setup:**
1. Wait ~2 minutes for SonarQube to initialize
2. Visit http://localhost:9000
3. Login with `admin` / `admin`, change password when prompted
4. Generate API token: User icon → My Account → Security → Generate Tokens
5. Add token to backend `.env`:
   ```env
   SONAR_TOKEN=your_generated_token
   ```

**Trivy Configuration** (in backend `.env`):
```env
TRIVY_ENABLED=true
TRIVY_SEVERITY=CRITICAL,HIGH,MEDIUM
TRIVY_TIMEOUT=300
TRIVY_SKIP_DIRS=node_modules,vendor,.git
```

## Docker Compose Deployment

Run the entire stack with Docker Compose:

```bash
# Set environment variables
export GITHUB_APP_ID=your_app_id
export GITHUB_CLIENT_ID=your_client_id
export GITHUB_CLIENT_SECRET=your_client_secret
export GITHUB_WEBHOOK_SECRET=your_webhook_secret
export SECRET_KEY=your_secret_key

# Start all services
docker-compose up -d
```

This starts:
- MongoDB, RabbitMQ, Redis (infrastructure)
- Backend API (port 8000)
- Frontend (port 3000)
- Celery Worker and Beat
- SonarQube (port 9000) and Trivy (port 4954)

## Remote Server Development

For resource-intensive tasks (SonarQube, Trivy, Celery workers), you can run all backend services on a remote server while developing API and Frontend locally.

### Server Setup

1. **On the remote server:**
   ```bash
   # Clone and setup
   git clone <repo-url>
   cd build-risk-dashboard
   ./scripts/setup-server.sh
   
   # Configure
   cp .env.server.example .env.server
   nano .env.server  # Fill in values
   
   # Start all services
   docker compose -f docker-compose.server.yml --env-file .env.server up -d
   ```

2. **On your local machine:**
   ```bash
   # Terminal 1: SSH port forward (keep open)
   ./scripts/ssh-forward-server.sh user@server-ip
   
   # Terminal 2: Backend API
   cd backend
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   
   # Terminal 3: Frontend
   cd frontend
   npm run dev
   ```

3. **Configure local `backend/.env`:**
   ```env
   MONGODB_URI=mongodb://localhost:27017
   CELERY_BROKER_URL=amqp://myuser:mypass@localhost:5672//
   REDIS_URL=redis://localhost:6379/0
   SONAR_HOST_URL=http://localhost:9000
   TRIVY_SERVER_URL=http://localhost:4954
   ```

### Ports Forwarded

| Local Port | Service |
|------------|---------|
| 27017 | MongoDB |
| 5672 | RabbitMQ (AMQP) |
| 15672 | RabbitMQ Management UI |
| 6379 | Redis |
| 9000 | SonarQube |
| 4954 | Trivy Server |

## Usage

### Initial Setup

1. **Login**: Use GitHub OAuth to log in
2. **Connect Repositories**: Go to the "Repositories" page and add your GitHub repositories
3. **Import**: The system will backfill workflow runs and start listening for webhooks

### Feature Extraction Pipeline

The platform uses [Hamilton](https://hamilton.dagworks.io/) for feature extraction. Features are organized in a DAG:

```
├── tasks/pipeline/
│   ├── hamilton_runner.py    # Pipeline executor
│   └── feature_dag/          # Feature module definitions
│       ├── build_features.py
│       ├── git_diff_features.py
│       ├── repo_features.py
│       └── ...
```

### SonarQube Integration

1. **Configure Scan Settings**:
   - Navigate to a repository detail page
   - Go to the "SonarQube" tab
   - Configure `sonar-project.properties` for the repository

2. **Trigger Scans**:
   - From the Builds page, click "Scan" next to any build
   - Or go to the SonarQube tab and view scan history

### Dataset Import & Enrichment

1. **Upload Dataset**: Import CSV datasets with build metadata
2. **Validate**: System validates repositories and builds
3. **Configure Features**: Select which features to extract
4. **Enrich**: Hamilton pipeline computes features for each build
5. **Export**: Download enriched dataset for ML training

## Development

### Backend

```bash
cd backend

# Run tests
uv run pytest

# Linting
uv run ruff check .

# Format code
uv run ruff format .

# Type checking
uv run mypy app/
```

### Frontend

```bash
cd frontend

# Lint
npm run lint

# Type check
npm run type-check

# Build
npm run build
```

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGODB_URI` | Yes | MongoDB connection string |
| `CELERY_BROKER_URL` | Yes | RabbitMQ connection URL |
| `REDIS_URL` | Yes | Redis connection URL |
| `GITHUB_APP_ID` | Yes | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | Yes | GitHub App private key (PEM) |
| `GITHUB_CLIENT_ID` | Yes | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | Yes | GitHub OAuth client secret |
| `GITHUB_WEBHOOK_SECRET` | Yes | Webhook signature secret |
| `SECRET_KEY` | Yes | JWT signing secret |
| `SONAR_TOKEN` | No | SonarQube API token |
| `TRIVY_ENABLED` | No | Enable Trivy scanning (default: false) |

## Troubleshooting

### MongoDB Connection Issues
```bash
# Check if containers are running
docker-compose ps

# View MongoDB logs
docker-compose logs mongo
```

### Celery Worker Not Processing Tasks
```bash
# Verify RabbitMQ is running
docker-compose ps rabbitmq

# Check worker logs
docker-compose logs celery-worker

# Test RabbitMQ connection
curl -u myuser:mypass http://localhost:15672/api/queues
```

### GitHub Webhook Issues
- Use ngrok for local webhook testing:
  ```bash
  ngrok http 8000
  ```
- Update GitHub App webhook URL to ngrok URL

### SonarQube Scan Failures
- Verify SonarQube server is accessible: http://localhost:9000
- Check scan job error messages in the UI
- Ensure `SONAR_TOKEN` is correctly set

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│  MongoDB    │
│  (Next.js)  │      │  (FastAPI)   │      │             │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
     ┌──────────┐    ┌──────────┐    ┌──────────┐
     │ RabbitMQ │    │  Redis   │    │ SonarQube│
     └──────────┘    └──────────┘    └──────────┘
            │
            ▼
     ┌──────────────────────────────────────────┐
     │           Celery Workers                 │
     │  ┌─────────┐  ┌──────────┐  ┌─────────┐  │
     │  │Ingestion│  │Processing│  │ Scanners│  │
     │  └─────────┘  └──────────┘  └─────────┘  │
     └──────────────────────────────────────────┘
```

## Features

- ✅ GitHub OAuth authentication
- ✅ Repository management and webhook integration
- ✅ Build log collection and analysis
- ✅ Git diff feature extraction
- ✅ Repository snapshot metrics
- ✅ Hamilton DAG-based feature pipeline
- ✅ Dataset import and enrichment workflow
- ✅ SonarQube code quality scanning
- ✅ Trivy security vulnerability scanning
- ✅ Configurable scan settings per repository
- ✅ Scan job tracking and retry mechanism
- ✅ Real-time WebSocket updates
- ✅ Pipeline execution monitoring

## Contributing

Please ensure all tests pass and code is properly formatted before submitting pull requests.

## License

MIT
