"""Repository management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pymongo.database import Database

from app.config import settings
from app.database.mongo import get_db
from app.models.schemas import (
    RepoImportRequest,
    RepoResponse,
    RepoScanRequest,
    GithubImportJobResponse,
)
from app.services.github_client import get_pipeline_github_client
from app.services.github_integration import create_import_job
from app.services.pipeline_store import PipelineStore
from app.tasks.repositories import enqueue_repo_import

router = APIRouter(prefix="/repos", tags=["Repositories"])


def _serialize_repo(doc: dict) -> RepoResponse:
    payload = doc.copy()
    payload["id"] = payload.pop("_id")
    return RepoResponse.model_validate(payload)


@router.post(
    "/import", response_model=RepoResponse, status_code=status.HTTP_201_CREATED
)
def import_repository(payload: RepoImportRequest, db: Database = Depends(get_db)):
    """Register a repository for ingestion."""
    owner_id = payload.user_id or settings.DEFAULT_REPO_OWNER_ID

    with get_pipeline_github_client(db, payload.installation_id) as gh:
        repo_data = gh.get_repository(payload.full_name)
        is_private = bool(repo_data.get("private"))

        # Validate that private repos have installation_id
        if is_private and not payload.installation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Private repositories require installation_id. Please install the GitHub App for this repository.",
            )

    store = PipelineStore(db)
    repo_doc = store.upsert_repository(
        user_id=owner_id,
        provider=payload.provider,
        full_name=payload.full_name,
        default_branch=repo_data.get("default_branch", "main"),
        is_private=bool(repo_data.get("private")),
        main_lang=repo_data.get("language"),
        github_repo_id=repo_data.get("id"),
        metadata=repo_data,
        installation_id=payload.installation_id,
        last_scanned_at=None,
    )
    return _serialize_repo(repo_doc)


@router.get("/", response_model=list[RepoResponse])
def list_repositories(
    db: Database = Depends(get_db),
    user_id: int | None = Query(default=None, description="Filter by owner id"),
):
    """List tracked repositories."""
    store = PipelineStore(db)
    repos = store.list_repositories(user_id=user_id)
    return [_serialize_repo(repo) for repo in repos]


@router.post(
    "/{repo_id}/scan",
    response_model=GithubImportJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_scan(
    repo_id: int = Path(..., description="Repository numeric id"),
    payload: RepoScanRequest | None = None,
    db: Database = Depends(get_db),
):
    """Trigger a scan job for the selected repository."""
    payload = payload or RepoScanRequest()
    store = PipelineStore(db)
    repo_doc = store.get_repository(repo_id)
    if not repo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )

    repo_full_name = repo_doc["full_name"]
    branch = repo_doc.get("default_branch") or "main"
    owner_id = repo_doc.get("user_id") or settings.DEFAULT_REPO_OWNER_ID
    installation_id = repo_doc.get("installation_id")
    if not installation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository missing installation id",
        )

    # Create an import/scan job and enqueue the snapshot task
    import_job = create_import_job(
        db,
        repository=repo_full_name,
        branch=branch,
        initiated_by=payload.initiated_by or "admin",
        user_id=owner_id,
        installation_id=installation_id,
    )
    job_id = import_job["id"]
    enqueue_repo_import.delay(repo_full_name, branch, job_id, owner_id, installation_id)
    return GithubImportJobResponse.model_validate(import_job)
