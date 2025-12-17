"""Admin-only repository access control API endpoints."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Path, Query
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.admin_repo import (
    AdminRepoListResponse,
    RepoAccessResponse,
    GrantAccessRequest,
    RevokeAccessRequest,
    VisibilityUpdateRequest,
)
from app.middleware.require_admin import require_admin
from app.services.admin_repo_service import AdminRepoService

router = APIRouter(prefix="/admin/repos", tags=["Admin - Repository Access"])


@router.get(
    "/",
    response_model=AdminRepoListResponse,
    response_model_by_alias=False,
)
def list_all_repos(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    visibility: Optional[Literal["public", "private"]] = Query(default=None),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """List all repositories with access info (Admin only)."""
    service = AdminRepoService(db)
    return service.list_repos(skip=skip, limit=limit, visibility=visibility)


@router.get(
    "/{repo_id}/access",
    response_model=RepoAccessResponse,
    response_model_by_alias=False,
)
def get_repo_access(
    repo_id: str = Path(..., description="Repository ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Get repository access details (Admin only). UC5: Grant Repository Access"""
    service = AdminRepoService(db)
    return service.get_repo_access(repo_id)


@router.post(
    "/{repo_id}/grant",
    response_model=RepoAccessResponse,
    response_model_by_alias=False,
)
def grant_repo_access(
    payload: GrantAccessRequest,
    repo_id: str = Path(..., description="Repository ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Grant users access to a repository (Admin only). UC5: Grant Repository Access"""
    service = AdminRepoService(db)
    return service.grant_access(repo_id, payload.user_ids)


@router.post(
    "/{repo_id}/revoke",
    response_model=RepoAccessResponse,
    response_model_by_alias=False,
)
def revoke_repo_access(
    payload: RevokeAccessRequest,
    repo_id: str = Path(..., description="Repository ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Revoke users' access from a repository (Admin only). UC5: Grant Repository Access"""
    service = AdminRepoService(db)
    return service.revoke_access(repo_id, payload.user_ids)


@router.patch(
    "/{repo_id}/visibility",
    response_model=RepoAccessResponse,
    response_model_by_alias=False,
)
def update_repo_visibility(
    payload: VisibilityUpdateRequest,
    repo_id: str = Path(..., description="Repository ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Update repository visibility (Admin only). UC5: Grant Repository Access"""
    service = AdminRepoService(db)
    return service.update_visibility(repo_id, payload.visibility)
