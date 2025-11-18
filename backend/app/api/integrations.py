"""Integration endpoints for third-party services."""

import json
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pymongo.database import Database

from app.config import settings
from app.database.mongo import get_db
from app.models.schemas import (
    GithubAuthorizeResponse,
    GithubImportJobResponse,
    GithubImportRequest,
    GithubInstallationListResponse,
    GithubInstallationResponse,
    GithubIntegrationStatusResponse,
    GithubOAuthInitRequest,
)
from app.services.github_integration import (
    create_import_job,
    get_github_status,
    list_import_jobs,
)
from app.services.github_webhook import handle_github_event, verify_signature
from app.services.github_oauth import (
    build_authorize_url,
    create_oauth_state,
    exchange_code_for_token,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/github", response_model=GithubIntegrationStatusResponse)
def get_github_integration_status(db: Database = Depends(get_db)):
    """Return the current GitHub OAuth integration status."""
    return get_github_status(db)


@router.post("/github/login", response_model=GithubAuthorizeResponse)
def initiate_github_login(
    payload: GithubOAuthInitRequest | None = Body(default=None),
    db: Database = Depends(get_db),
):
    """Initiate GitHub OAuth flow by creating a state token."""
    payload = payload or GithubOAuthInitRequest()
    oauth_state = create_oauth_state(db, redirect_url=payload.redirect_path)
    authorize_url = build_authorize_url(oauth_state["_id"])
    return {"authorize_url": authorize_url, "state": oauth_state["_id"]}


@router.post("/github/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_github_token(db: Database = Depends(get_db)):
    """Remove stored GitHub access tokens."""
    result = db.github_connection.delete_many({})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy token để thu hồi.",
        )


@router.get("/github/callback")
async def github_oauth_callback(
    code: str = Query(..., description="GitHub authorization code"),
    state: str = Query(..., description="GitHub OAuth state token"),
    db: Database = Depends(get_db),
):
    """Handle GitHub OAuth callback, exchange code for token, and redirect to frontend."""
    _, redirect_path = await exchange_code_for_token(db, code=code, state=state)
    redirect_target = settings.FRONTEND_BASE_URL.rstrip("/")
    if redirect_path:
        redirect_target = f"{redirect_target}{redirect_path}"
    else:
        redirect_target = f"{redirect_target}/integrations/github?status=success"
    return RedirectResponse(url=redirect_target)


@router.get("/github/imports", response_model=List[GithubImportJobResponse])
def list_github_import_jobs(db: Database = Depends(get_db)):
    """List history of GitHub repository import jobs."""
    return list_import_jobs(db)


@router.post(
    "/github/imports",
    response_model=GithubImportJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_github_import(payload: GithubImportRequest, db: Database = Depends(get_db)):
    """Create a mock import job for a repository."""
    initiated_by = payload.initiated_by or "admin"
    owner_user_id = payload.user_id or settings.DEFAULT_REPO_OWNER_ID
    return create_import_job(
        db,
        repository=payload.repository,
        branch=payload.branch,
        initiated_by=initiated_by,
        user_id=owner_user_id,
    )


@router.post("/github/webhook")
async def github_webhook(request: Request, db: Database = Depends(get_db)):
    """Receive GitHub webhook events for workflow runs."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event = request.headers.get("X-GitHub-Event", "")
    verify_signature(signature, body)

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - invalid payload
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload"
        ) from exc

    return handle_github_event(db, event, payload)


@router.get("/github/installations", response_model=GithubInstallationListResponse)
def list_github_installations(db: Database = Depends(get_db)):
    """List all GitHub App installations."""
    installations = list(db.github_installations.find().sort("installed_at", -1))
    return {"installations": installations}


@router.get(
    "/github/installations/{installation_id}", response_model=GithubInstallationResponse
)
def get_github_installation(installation_id: str, db: Database = Depends(get_db)):
    """Get details of a specific GitHub App installation."""
    installation = db.github_installations.find_one({"_id": installation_id})
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Installation {installation_id} not found",
        )
    return installation
