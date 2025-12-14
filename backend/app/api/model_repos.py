from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status, Body
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSuggestionListResponse,
    RepoSearchResponse,
    RepoUpdateRequest,
)
from app.dtos.build import BuildListResponse, BuildDetail
from app.middleware.auth import get_current_user
from app.services.build_service import BuildService
from app.services.repository_service import RepositoryService

router = APIRouter(prefix="/repos", tags=["Repositories"])


@router.post(
    "/import/bulk",
    response_model=List[RepoResponse],
    response_model_by_alias=False,
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


@router.get("/languages")
def detect_repository_languages(
    full_name: str = Query(..., description="Repository full name (owner/repo)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Detect repository languages via GitHub API (/repos/{owner}/{repo}/languages).

    Returns top 5 languages (lowercase), falling back to empty list on failure.
    """
    service = RepositoryService(db)
    return service.detect_languages(full_name, current_user)


@router.get("/test-frameworks")
def list_test_frameworks(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List supported test frameworks for log parsing.

    Returns:
        - frameworks: List of all supported framework names
        - by_language: Frameworks grouped by language
        - languages: List of languages with test framework support

    Use this to drive UI selection when importing repositories.
    """
    service = RepositoryService(db)
    return service.list_test_frameworks()


@router.get("/", response_model=RepoListResponse, response_model_by_alias=False)
def list_repositories(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search query"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List tracked repositories with pagination."""
    user_id = str(current_user["_id"])
    service = RepositoryService(db)
    return service.list_repositories(user_id, skip, limit, q)


@router.get("/search", response_model=RepoSearchResponse)
def search_repositories(
    q: str | None = Query(
        default=None,
        description="Search query",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Search for repositories (private installed and public)."""
    user_id = str(current_user["_id"])
    service = RepositoryService(db)
    return service.search_repositories(user_id, q)


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


@router.get(
    "/{repo_id}", response_model=RepoDetailResponse, response_model_by_alias=False
)
def get_repository_detail(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = RepositoryService(db)
    return service.get_repository_detail(repo_id, current_user)


@router.patch(
    "/{repo_id}", response_model=RepoDetailResponse, response_model_by_alias=False
)
def update_repository_settings(
    repo_id: str,
    payload: RepoUpdateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = RepositoryService(db)
    return service.update_repository_settings(repo_id, payload, current_user)


@router.post("/{repo_id}/sync-run")
def trigger_sync(
    repo_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Trigger a manual sync for the repository."""
    user_id = str(current_user["_id"])
    service = RepositoryService(db)
    return service.trigger_sync(repo_id, user_id)


@router.post("/{repo_id}/reprocess-features")
def trigger_reprocess_features(
    repo_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    service = RepositoryService(db)
    return service.trigger_reprocess(repo_id)


@router.get(
    "/{repo_id}/builds",
    response_model=BuildListResponse,
    response_model_by_alias=False,
)
def get_repo_builds(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search query"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List builds for a repository."""
    service = BuildService(db)
    return service.get_builds_by_repo(repo_id, skip, limit, q)


@router.get(
    "/{repo_id}/builds/{build_id}",
    response_model=BuildDetail,
    response_model_by_alias=False,
)
def get_build_detail(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    build_id: str = Path(..., description="Build id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get build details."""
    service = BuildService(db)
    build = service.get_build_detail(build_id)
    if not build:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Build not found")
    return build


@router.post(
    "/{repo_id}/builds/{build_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_build(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    build_id: str = Path(..., description="Build id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Reprocess a build using the new DAG-based feature pipeline.

    Useful for:
    - Retrying failed builds
    - Re-extracting features after pipeline updates
    - Testing new feature extractors on existing data
    """
    service = RepositoryService(db)
    return service.reprocess_build(repo_id, build_id, current_user)
