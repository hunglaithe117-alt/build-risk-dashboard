"""Repository management endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Path, Query, status
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
from app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repos", tags=["Repositories"])


@router.post(
    "/sync", response_model=RepoSuggestionListResponse, status_code=status.HTTP_200_OK
)
def sync_repositories(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Sync available repositories from GitHub App Installations."""
    user_id = str(current_user["_id"])
    service = RepositoryService(db)
    return service.sync_repositories(user_id, limit)


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
    return service.bulk_import_repositories(user_id, payloads)


@router.get("/", response_model=List[RepoResponse])
def list_repositories(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List tracked repositories."""
    service = RepositoryService(db)
    return service.list_repositories(current_user["_id"])


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
    user_id = str(current_user["_id"])
    service = RepositoryService(db)
    return service.discover_repositories(user_id, q, limit)


@router.get("/{repo_id}", response_model=RepoDetailResponse)
def get_repository_detail(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = RepositoryService(db)
    return service.get_repository_detail(repo_id, current_user)


@router.patch("/{repo_id}", response_model=RepoDetailResponse)
def update_repository_settings(
    repo_id: str,
    payload: RepoUpdateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = RepositoryService(db)
    return service.update_repository_settings(repo_id, payload, current_user)
