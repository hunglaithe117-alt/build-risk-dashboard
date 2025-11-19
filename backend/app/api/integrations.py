"""Integration endpoints for third-party services."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    GithubInstallationListResponse,
    GithubInstallationResponse,
)
from app.middleware.auth import get_current_user
from app.services.github.github_webhook import handle_github_event, verify_signature

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/github/installations", response_model=GithubInstallationListResponse)
def list_github_installations(
    db: Database = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    """List all GitHub App installations."""
    installations = list(db.github_installations.find().sort("installed_at", -1))
    return {"installations": installations}


@router.get(
    "/github/installations/{installation_id}", response_model=GithubInstallationResponse
)
def get_github_installation(
    installation_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get details of a specific GitHub App installation."""
    installation = db.github_installations.find_one({"_id": installation_id})
    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Installation {installation_id} not found",
        )
    return installation
