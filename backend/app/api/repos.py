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
from app.services.github.github_client import get_pipeline_github_client
from app.services.pipeline_exceptions import (
    PipelineConfigurationError,
    PipelineRetryableError,
)
from app.services.pipeline_store_service import PipelineStore

router = APIRouter(prefix="/repos", tags=["Repositories"])


def _prepare_repo_payload(doc: dict) -> dict:
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
    "/import", response_model=RepoResponse, status_code=status.HTTP_201_CREATED
)
def import_repository(
    payload: RepoImportRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Register a repository for ingestion."""
    # Use authenticated user's ID if not provided in payload
    user_id = payload.user_id or str(current_user["_id"])

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
    return _serialize_repo(repo_doc)


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
        description="Optional search query for public repositories",
    ),
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
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
                    # Add is:private to the query to search only for private repos
                    repos = gh.search_repositories(f"{query} is:private", per_page=limit)
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
            detail="You don't have permission to access this repository"
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
            detail="You don't have permission to update this repository"
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
