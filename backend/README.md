# BuildGuard Backend

FastAPI backend service for the BuildGuard DevSecOps dashboard. This service exposes mocked data for CI/CD build telemetry, integrates with GitHub OAuth (read-only), and is managed using [uv](https://github.com/astral-sh/uv) for dependency management. Model/prediction features are temporarily disabled.

## Quick start with uv

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The default configuration uses MongoDB (`mongodb://localhost:27017/buildguard`). Update `backend/.env` nếu bạn dùng connection khác. Mock data sẽ tự seed khi khởi động server.

### Useful commands

```bash

# Run unit tests / linters (extras defined in pyproject)
uv run pytest
uv run ruff check .
```

### GitHub OAuth setup

Add the following variables to `.env` (see `.env.example`):

```
GITHUB_CLIENT_ID=<github-oauth-app-client-id>
GITHUB_CLIENT_SECRET=<github-oauth-app-client-secret>
GITHUB_REDIRECT_URI=http://localhost:8000/api/integrations/github/callback
FRONTEND_BASE_URL=http://localhost:3000
```

Start the backend then visit `http://localhost:3000/integrations/github` to trigger the OAuth flow.

### Key endpoints

- `GET /api/builds/` – Paginated builds including full telemetry (commits, workflows, features)
- `GET /api/dashboard/summary` – Aggregated metrics for dashboard widgets
- `GET /api/integrations/github` – GitHub OAuth status + repository summary
