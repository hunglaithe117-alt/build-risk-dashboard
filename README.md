# Build Risk Assessment System

This project is a comprehensive system for assessing build risks in CI/CD pipelines. It consists of a FastAPI backend with Celery for asynchronous processing and a Next.js frontend.

## Prerequisites

- **Docker & Docker Compose**: For running infrastructure services (MongoDB, RabbitMQ, Redis).
- **Python 3.10+**: For the backend. Recommended to use `uv` for package management.
- **Node.js 18+**: For the frontend.
- **GitHub App**: You need a GitHub App for authentication and webhooks.

## Project Structure

- `backend/`: FastAPI application, Celery workers, and domain logic.
- `frontend/`: Next.js web application.
- `docker-compose.yml`: Infrastructure definitions.

## Setup & Running

### 1. Infrastructure

Start the required databases and message brokers:

```bash
docker-compose up -d
```

This will start:
- MongoDB (port 27017)
- RabbitMQ (ports 5672, 15672)
- Redis (port 6379)

### 2. Backend Setup

1.  Navigate to the backend directory:
    ```bash
    cd backend
    ```

2.  Create a `.env` file based on your configuration. You need to configure GitHub App credentials:
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
    ```

3.  Install dependencies and run the API server:
    ```bash
    # Using uv (recommended)
    uv sync
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```

4.  Run the Celery worker (in a separate terminal):
    ```bash
    cd backend
    uv run celery -A app.celery_app worker -Q import_repo,collect_workflow_logs,data_processing,pipeline.default --loglevel=info
    ```
    *Note: The queues `import_repo`, `collect_workflow_logs`, and `data_processing` are essential for the pipeline.*

### 3. Frontend Setup

1.  Navigate to the frontend directory:
    ```bash
    cd frontend
    ```

2.  Install dependencies:
    ```bash
    npm install
    # or
    yarn install
    ```

3.  Create a `.env.local` file (optional, defaults usually work for local dev):
    ```env
    NEXT_PUBLIC_API_URL=http://localhost:8000/api
    ```

4.  Run the development server:
    ```bash
    npm run dev
    ```

5.  Open [http://localhost:3000](http://localhost:3000) in your browser.

## Usage

1.  **Login**: Use GitHub OAuth to log in.
2.  **Connect Repositories**: Go to the "Repositories" page and connect your GitHub repositories.
3.  **Import**: The system will backfill workflow runs and start listening for webhooks.
4.  **Analysis**: The pipeline will process builds, extracting logs, diffs, and repository snapshots to assess risk.

## Development

- **Backend Tests**: `uv run pytest`
- **Linting**: `uv run ruff check .`
