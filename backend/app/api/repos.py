"""Repository management endpoints."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    GithubImportJobResponse,
    RepoDetailResponse,
    RepoImportRequest,
    RepoResponse,
    RepoScanRequest,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
)
from app.services.github_client import get_pipeline_github_client
from app.services.github_integration_service import create_import_job
from app.services.pipeline_exceptions import (
    PipelineConfigurationError,
    PipelineRetryableError,
)
from app.services.pipeline_store_service import PipelineStore
from app.tasks.repositories import enqueue_repo_import

router = APIRouter(prefix="/repos", tags=["Repositories"])


def _prepare_repo_payload(doc: dict, build_count: int | None = None) -> dict:
    """Prepare repository document for Pydantic validation with computed fields."""
    payload = doc.copy()
    # PyObjectId in Pydantic will auto-handle _id and user_id conversion

    # Set defaults for optional fields
    payload.setdefault("ci_provider", "github_actions")
    payload.setdefault("monitoring_enabled", True)
    payload.setdefault("sync_status", "healthy")
    payload.setdefault("webhook_status", "inactive")
    payload.setdefault("ci_token_status", "valid")

    # Normalize tracked branches
    branches = payload.get("tracked_branches") or []
    default_branch = payload.get("default_branch")
    if not branches and default_branch:
        branches = [default_branch]
    payload["tracked_branches"] = branches

    # Sync status logic
    if payload.get("monitoring_enabled") is False:
        payload["sync_status"] = "disabled"

    # Computed field: build count
    payload["total_builds_imported"] = (
        build_count
        if build_count is not None
        else payload.get("total_builds_imported", 0)
    )
    return payload


def _serialize_repo(doc: dict, build_count: int | None = None) -> RepoResponse:
    return RepoResponse.model_validate(_prepare_repo_payload(doc, build_count))


def _serialize_repo_detail(
    doc: dict, build_count: int | None = None
) -> RepoDetailResponse:
    payload = _prepare_repo_payload(doc, build_count)
    payload["metadata"] = doc.get("metadata")
    return RepoDetailResponse.model_validate(payload)


def _normalize_branches(branches: List[str]) -> List[str]:
    seen: Dict[str, bool] = {}
    normalized: List[str] = []
    for branch in branches:
        value = (branch or "").strip()
        if not value or value in seen:
            continue
        seen[value] = True
        normalized.append(value)
    return normalized


@router.post(
    "/import", response_model=RepoResponse, status_code=status.HTTP_201_CREATED
)
def import_repository(payload: RepoImportRequest, db: Database = Depends(get_db)):
    """Register a repository for ingestion."""
    user_id = payload.user_id

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
        user_id=user_id,
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
    return _serialize_repo(repo_doc, build_count=0)


@router.get("/", response_model=list[RepoResponse])
def list_repositories(
    db: Database = Depends(get_db),
    user_id: str | None = Query(default=None, description="Filter by owner id"),
):
    """List tracked repositories."""
    store = PipelineStore(db)
    repos = store.list_repositories(user_id=user_id)
    counts = store.count_builds_by_repository()
    return [
        _serialize_repo(repo, counts.get(repo.get("full_name"), 0)) for repo in repos
    ]


@router.get("/available", response_model=RepoSuggestionListResponse)
def discover_repositories(
    q: str | None = Query(
        default=None,
        description="Optional search query for public repositories",
    ),
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_db),
):
    """List GitHub repositories available to connect."""
    store = PipelineStore(db)
    tracked = {repo.get("full_name") for repo in store.list_repositories()}
    query = (q or "").strip()
    try:
        with get_pipeline_github_client(db) as gh:
            if query:
                if "/" in query:
                    repos = [gh.get_repository(query)]
                else:
                    repos = gh.search_repositories(query, per_page=limit)
                source = "search"
            else:
                repos = gh.list_authenticated_repositories(per_page=limit)
                source = "owned"
    except (
        PipelineConfigurationError
    ) as exc:  # pragma: no cover - runtime config errors
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except PipelineRetryableError as exc:  # pragma: no cover - runtime API errors
        if query and "/" in query:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{query}' not found or inaccessible.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    items = []
    for repo in repos[:limit]:
        full_name = repo.get("full_name")
        if not full_name:
            continue
        owner = (repo.get("owner") or {}).get("login")
        items.append(
            {
                "full_name": full_name,
                "description": repo.get("description"),
                "default_branch": repo.get("default_branch"),
                "private": bool(repo.get("private")),
                "owner": owner,
                "installed": full_name in tracked,
                "requires_installation": bool(repo.get("private")),
                "source": source,
            }
        )

    return RepoSuggestionListResponse(items=items)


@router.get("/{repo_id}", response_model=RepoDetailResponse)
def get_repository_detail(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
):
    store = PipelineStore(db)
    repo_doc = store.get_repository(repo_id)
    if not repo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )
    build_count = store.count_builds_for_repo(repo_doc.get("full_name"))
    return _serialize_repo_detail(repo_doc, build_count)


@router.patch("/{repo_id}", response_model=RepoDetailResponse)
def update_repository_settings(
    repo_id: str,
    payload: RepoUpdateRequest,
    db: Database = Depends(get_db),
):
    store = PipelineStore(db)
    repo_doc = store.get_repository(repo_id)
    if not repo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )

    updates = payload.model_dump(exclude_unset=True)
    if "tracked_branches" in updates:
        updates["tracked_branches"] = _normalize_branches(
            updates.get("tracked_branches") or []
        )
    default_branch = updates.get("default_branch")
    if default_branch:
        existing_branches = updates.get("tracked_branches") or repo_doc.get(
            "tracked_branches", []
        )
        if default_branch not in existing_branches:
            updates["tracked_branches"] = _normalize_branches(
                existing_branches + [default_branch]
            )

    if not updates:
        updated = repo_doc
    else:
        updated = store.update_repository(repo_id, updates)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

    build_count = store.count_builds_for_repo(updated.get("full_name"))
    return _serialize_repo_detail(updated, build_count)


@router.get(
    "/{repo_id}/jobs",
    response_model=list[GithubImportJobResponse],
)
def list_repository_jobs(
    repo_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    store = PipelineStore(db)
    repo_doc = store.get_repository(repo_id)
    if not repo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )
    jobs = store.list_repo_jobs(repo_doc.get("full_name"), limit=limit)
    return [GithubImportJobResponse.model_validate(job) for job in jobs]


@router.post(
    "/{repo_id}/scan",
    response_model=GithubImportJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_scan(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
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
    user_id = repo_doc.get("user_id")
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
        user_id=user_id,
        installation_id=installation_id,
    )
    job_id = import_job["id"]
    enqueue_repo_import.delay(repo_full_name, branch, job_id, user_id, installation_id)
    return GithubImportJobResponse.model_validate(import_job)
