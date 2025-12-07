from typing import List

from fastapi import APIRouter, Depends, Path, Query, status, Body
from pymongo.database import Database
from bson import ObjectId

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
from app.services.github.github_client import (
    get_app_github_client,
    get_user_github_client,
)
from app.services.extracts.log_parser import TestLogParser

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
    installation_id = None
    repo_repo = RepositoryService(db).repo_repo
    imported = repo_repo.find_by_full_name("github", full_name)
    if imported and imported.installation_id:
        installation_id = imported.installation_id

    # Prefer installation if available, else fallback to user token, else public
    if installation_id:
        client_ctx = get_app_github_client(db, installation_id)
    else:
        client_ctx = get_user_github_client(db, str(current_user["_id"]))

    languages: list[str] = []
    try:
        with client_ctx as gh:
            stats = gh.list_languages(full_name) or {}
            languages = [
                lang.lower()
                for lang, _ in sorted(
                    stats.items(), key=lambda kv: kv[1], reverse=True
                )[:5]
            ]
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to detect languages for %s: %s", full_name, e
        )

    return {"languages": languages}


@router.get("/test-frameworks")
def list_test_frameworks(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List supported test frameworks for log parsing.

    Use this to drive UI selection when importing repositories.
    """
    return {"by_language": TestLogParser.FRAMEWORKS_BY_LANG}


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
    """
    Re-extract features for all existing builds.

    Unlike sync-run (which fetches new workflow runs from GitHub),
    this endpoint reprocesses existing builds to re-extract features.
    Useful when feature extractors have been updated.
    """
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
    from fastapi import HTTPException
    from app.tasks.processing import reprocess_build as reprocess_build_task

    service = BuildService(db)
    build = service.get_build_detail(build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")

    # Trigger async reprocessing
    reprocess_build_task.delay(build_id)

    return {
        "status": "queued",
        "build_id": build_id,
        "message": "Build reprocessing has been queued",
    }


# --- SonarQube Integration Endpoints ---


@router.post("/{repo_id}/sonar/config")
async def update_sonar_config(
    repo_id: str,
    payload: dict = Body(..., embed=True),  # Expect {"content": "..."}
    db: Database = Depends(get_db),
):
    """Update sonar-project.properties content for the repository."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    content = payload.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="Content is required")

    success = service.update_config(repo_id, content)
    if not success:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {"status": "success"}


@router.get("/{repo_id}/sonar/config")
async def get_sonar_config(
    repo_id: str,
    db: Database = Depends(get_db),
):
    """Get sonar-project.properties content."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    content = service.get_config(repo_id)
    return {"content": content or ""}


@router.get("/{repo_id}/sonar/jobs")
async def list_scan_jobs(
    repo_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    """List scan jobs for the repository."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    return service.list_jobs(repo_id, skip, limit)


@router.post("/{repo_id}/builds/{build_id}/scan")
async def trigger_build_scan(
    repo_id: str,
    build_id: str,
    db: Database = Depends(get_db),
):
    """Trigger a SonarQube scan for a specific build."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    try:
        job = service.trigger_scan(build_id)
        return {"status": "queued", "job_id": str(job.id)}
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail=str(e))

    from app.services.sonar_service import SonarService

    service = SonarService(db)
    try:
        job = service.retry_job(job_id)
        return {"status": "queued", "job_id": str(job.id)}
    except ValueError as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sonar/jobs/{job_id}/retry")
async def retry_scan_job(
    job_id: str,
    payload: dict = Body(default={"config_override": None}),
    db: Database = Depends(get_db),
):
    """Retry a failed scan job."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    try:
        config_override = payload.get("config_override")
        job = service.retry_job(job_id, config_override=config_override)
        return {"status": "queued", "job_id": str(job.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{repo_id}/sonar/results")
async def list_scan_results(
    repo_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    """List scan results (metrics) for the repository."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    return service.list_results(repo_id, skip, limit)


@router.get("/{repo_id}/sonar/failed")
async def list_failed_scans(
    repo_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    """List failed scans that need attention."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    return service.list_failed_scans(repo_id, skip, limit)


@router.put("/sonar/failed/{failed_scan_id}/config")
async def update_failed_scan_config(
    failed_scan_id: str,
    payload: dict = Body(..., embed=True),  # {"content": "..."}
    db: Database = Depends(get_db),
):
    """Update configuration override for a failed scan."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    content = payload.get("content")
    if content is None:
        raise HTTPException(status_code=400, detail="Content is required")

    try:
        failed_scan = service.update_failed_scan_config(failed_scan_id, content)
        return {"status": "success", "failed_scan_id": str(failed_scan.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sonar/failed/{failed_scan_id}/retry")
async def retry_failed_scan(
    failed_scan_id: str,
    db: Database = Depends(get_db),
):
    """Retry a failed scan with its configuration override."""
    from app.services.sonar_service import SonarService

    service = SonarService(db)
    try:
        result = service.retry_failed_scan(failed_scan_id)
        return {"status": "queued", "job_id": str(result.id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
