"""Repository management endpoints."""

from __future__ import annotations

from typing import Dict, List

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoResponse,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
)
from app.middleware.auth import get_current_user
from app.services.github.github_sync import sync_user_available_repos
from app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repos", tags=["Repositories"])


def _prepare_repo_payload(doc: dict) -> dict:
    payload = doc.copy()

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

    payload["total_builds_imported"] = payload.get("total_builds_imported", 0)
    return payload


def _serialize_repo(doc: dict) -> RepoResponse:
    return RepoResponse.model_validate(_prepare_repo_payload(doc))


def _serialize_repo_detail(doc: dict) -> RepoDetailResponse:
    payload = _prepare_repo_payload(doc)
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
    "/sync", response_model=RepoSuggestionListResponse, status_code=status.HTTP_200_OK
)
def sync_repositories(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Sync available repositories from GitHub App Installations."""
    user_id = str(current_user["_id"])
    store = PipelineStore(db)

    try:
        sync_user_available_repos(db, user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to sync repositories: {str(e)}",
        )

    return discover_repositories(db=db, current_user=current_user, q=None, limit=50)


@router.post(
    "/import", response_model=RepoResponse, status_code=status.HTTP_201_CREATED
)
def import_repository(
    payload: RepoImportRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Register a repository for ingestion."""
    user_id = payload.user_id or str(current_user["_id"])
    service = RepositoryService(db)

    repo_doc = service.import_repository(user_id, payload)

    return _serialize_repo(repo_doc)


@router.post(
    "/import/bulk",
    response_model=List[RepoResponse],
    status_code=status.HTTP_201_CREATED,
)
def bulk_import_repositories(
    payloads: List[RepoImportRequest],
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Register multiple repositories for ingestion."""
    user_id = str(current_user["_id"])
    service = RepositoryService(db)

    results = service.bulk_import_repositories(user_id, payloads)

    return [_serialize_repo(doc) for doc in results]


@router.get("/", response_model=list[RepoResponse])
def list_repositories(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    user_id: str | None = Query(default=None, description="Filter by owner id"),
):
    """List tracked repositories."""
    # If user_id not specified, default to current user's repositories
    filter_user_id = user_id or str(current_user["_id"])

    store = PipelineStore(db)
    repos = store.list_repositories(user_id=filter_user_id)
    return [_serialize_repo(repo) for repo in repos]


@router.get("/available", response_model=RepoSuggestionListResponse)
def discover_repositories(
    q: str | None = Query(
        default=None,
        description="Optional filter by name",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List available repositories."""
    store = PipelineStore(db)
    user_id = str(current_user["_id"])

    items = store.discover_available_repositories(user_id=user_id, q=q, limit=limit)

    return RepoSuggestionListResponse(items=items)


@router.get("/{repo_id}", response_model=RepoDetailResponse)
def get_repository_detail(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    store = PipelineStore(db)
    repo_doc = store.get_repository(repo_id)
    if not repo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )

    # Verify user owns this repository
    repo_user_id = str(repo_doc.get("user_id", ""))
    current_user_id = str(current_user["_id"])
    if repo_user_id != current_user_id and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this repository",
        )

    return _serialize_repo_detail(repo_doc)


@router.patch("/{repo_id}", response_model=RepoDetailResponse)
def update_repository_settings(
    repo_id: str,
    payload: RepoUpdateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    store = PipelineStore(db)
    repo_doc = store.get_repository(repo_id)
    if not repo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        )

    # Verify user owns this repository
    repo_user_id = str(repo_doc.get("user_id", ""))
    current_user_id = str(current_user["_id"])
    if repo_user_id != current_user_id and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this repository",
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

    return _serialize_repo_detail(updated)
