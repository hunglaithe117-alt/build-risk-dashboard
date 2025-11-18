"""Integration endpoints for third-party services."""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    GithubImportJobResponse,
    GithubImportRequest,
    GithubInstallationListResponse,
    GithubInstallationResponse,
)
from app.services.github_integration_service import (
    create_import_job,
    list_import_jobs,
)
from app.services.github_webhook import handle_github_event, verify_signature

router = APIRouter(prefix="/integrations", tags=["Integrations"])


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
    owner_user_id = payload.user_id
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
