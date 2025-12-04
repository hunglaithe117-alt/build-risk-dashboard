# Build Risk UI

A comprehensive CI/CD risk assessment platform with SonarQube code quality integration.

## Prerequisites

- **Docker & Docker Compose**: For running infrastructure services (MongoDB, RabbitMQ, Redis)
- **Python 3.10+**: For the backend. Recommended to use `uv` for package management
- **Node.js 18+**: For the frontend
- **GitHub App**: Required for authentication and webhooks
- **SonarQube Server** (Optional): For code quality scanning. Can use local instance or cloud service

## Project Structure

- `backend/`: FastAPI application, Celery workers, and domain logic
- `frontend/`: Next.js web application
- `docker-compose.yml`: Infrastructure definitions

## Local Development Setup

### 1. Infrastructure

Start the required databases and message brokers:

```bash
docker-compose up -d
```

This will start:
- MongoDB (port 27017)
- RabbitMQ (ports 5672, 15672)
- Redis (port 6379)

**RabbitMQ Management Console**: [http://localhost:15672](http://localhost:15672) (default: `myuser` / `mypass`)

### 2. SonarQube Server (Optional)

If you want to use SonarQube scanning, you have two options:

#### Option A: Local SonarQube with Docker

```bash
docker run -d --name sonarqube -p 9000:9000 sonarqube:latest
```

Then visit [http://localhost:9000](http://localhost:9000) (default login: `admin` / `admin`).

Generate a token: User → My Account → Security → Generate Tokens

#### Option B: Use SonarCloud

Sign up at [sonarcloud.io](https://sonarcloud.io) and obtain your organization token.

### 3. Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a `.env` file with the following configuration:
   ```env
   # Database
   MONGODB_URI=mongodb://localhost:27017
   MONGODB_DB_NAME=buildguard

   # Celery / RabbitMQ / Redis
   CELERY_BROKER_URL=amqp://myuser:mypass@localhost:5672//
   REDIS_URL=redis://localhost:6379/0

   # GitHub App Configuration
   GITHUB_APP_ID=your_app_id
   GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY----- ... "
   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   GITHUB_WEBHOOK_SECRET=your_webhook_secret
   
   # Auth
   SECRET_KEY=your_secret_key
   
   # SonarQube Configuration (Optional)
   SONAR_HOST_URL=http://localhost:9000
   SONAR_TOKEN=your_sonarqube_token
   SONAR_DEFAULT_PROJECT_KEY=build-risk-ui
   
   # Repository Mirror (for SonarQube scanning)
   REPO_MIRROR_ROOT=/tmp/build-risk-repos
   ```

3. Install dependencies:
   ```bash
   # Using uv (recommended)
   uv sync
   ```

4. Run the API server:
   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   API will be available at [http://localhost:8000](http://localhost:8000)
   
   API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

5. Run Celery worker (in a separate terminal):
   ```bash
   cd backend
   uv run celery -A app.celery_app worker --loglevel=info
   ```

   **Queues explained:**
   - `import_repo`: Repository import and workflow sync
   - `collect_workflow_logs`: Build log collection
   - `data_processing`: Feature extraction pipeline
   - `pipeline.default`: SonarQube scanning tasks

### 4. Frontend Setup

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

5. Open [http://localhost:3000](http://localhost:3000) in your browser

## Usage

### Initial Setup

1. **Login**: Use GitHub OAuth to log in
2. **Connect Repositories**: Go to the "Repositories" page and add your GitHub repositories
3. **Import**: The system will backfill workflow runs and start listening for webhooks

### SonarQube Integration

1. **Configure Scan Settings**:
   - Navigate to a repository detail page
   - Go to the "SonarQube" tab
   - Configure `sonar-project.properties` for the repository
   
   Example configuration:
   ```properties
   sonar.projectKey=my-project
   sonar.sources=.
   sonar.sourceEncoding=UTF-8
   sonar.exclusions=**/node_modules/**,**/dist/**,**/build/**
   sonar.java.binaries=.
   ```

2. **Trigger Scans**:
   - From the Builds page, click "Scan" next to any build
   - Or go to the SonarQube tab and view scan history
   
3. **Monitor Progress**:
   - Scan jobs table shows real-time status
   - Retry failed scans with one click
   - View error messages for debugging

### Analysis Pipeline

The system automatically:
- Processes builds upon webhook triggers
- Extracts logs, Git diffs, and repository snapshots
- Computes risk metrics
- Optionally runs SonarQube analysis for code quality

## Development

### Backend

- **Run tests**: 
  ```bash
  cd backend
  uv run pytest
  ```

- **Linting**: 
  ```bash
  uv run ruff check .
  ```

- **Format code**: 
  ```bash
  uv run ruff format .
  ```

### Frontend

- **Lint**: 
  ```bash
  cd frontend
  npm run lint
  ```

- **Type check**: 
  ```bash
  npm run type-check
  ```

## Troubleshooting

### MongoDB Connection Issues
- Ensure Docker containers are running: `docker-compose ps`
- Check MongoDB logs: `docker-compose logs mongodb`

### Celery Worker Not Processing Tasks
- Verify RabbitMQ is running: `docker-compose ps rabbitmq`
- Check worker logs for queue configuration
- Ensure `CELERY_BROKER_URL` in `.env` is correct

### SonarQube Scan Failures
- Verify `sonar-scanner` is installed in your PATH
  ```bash
  sonar-scanner --version
  ```
- Check SonarQube server is accessible
- Review scan job error messages in the UI
- Ensure repository configuration is valid

### GitHub Webhook Issues
- Use ngrok for local webhook testing:
  ```bash
  ngrok http 8000
  ```
- Update GitHub App webhook URL to ngrok URL

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│  MongoDB    │
│  (Next.js)  │      │  (FastAPI)   │      │             │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   RabbitMQ   │
                     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐      ┌──────────────┐
                     │Celery Workers│─────▶│  SonarQube   │
                     │              │      │   Server     │
                     └──────────────┘      └──────────────┘
```

## Features

- ✅ GitHub OAuth authentication
- ✅ Repository management and webhook integration
- ✅ Build log collection and analysis
- ✅ Git diff feature extraction
- ✅ Repository snapshot metrics
- ✅ SonarQube code quality scanning
- ✅ Configurable scan settings per repository
- ✅ Scan job tracking and retry mechanism
- ✅ Real-time WebSocket updates

## Contributing

Please ensure all tests pass and code is properly formatted before submitting pull requests.

## License

MIT
