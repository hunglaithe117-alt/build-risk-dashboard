from typing import List

from fastapi import APIRouter, Depends, Path, Query, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSearchResponse,
    RepoSuggestionListResponse,
)
from app.dtos.build import (
    BuildDetail,
    BuildListResponse,
    ImportBuildListResponse,
    TrainingBuildListResponse,
    UnifiedBuildListResponse,
)
from app.middleware.auth import get_current_user
from app.middleware.rbac import Permission, RequirePermission
from app.services.model_build_service import ModelBuildService
from app.services.model_repository_service import RepositoryService

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
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_REPOS)),
):
    """Register multiple repositories for ingestion (Admin only)."""
    user_id = str(_admin["_id"])
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


@router.get("/", response_model=RepoListResponse, response_model_by_alias=False)
def list_repositories(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search query"),
    status: str | None = Query(default=None, description="Filter by status"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List tracked repositories with RBAC access control."""
    service = RepositoryService(db)
    return service.list_repositories(current_user, skip, limit, q, status)


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


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repository(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_REPOS)),
):
    """
    Permanently delete a repository configuration (Admin only).

    Cascade deletes:
    - All ModelImportBuild records
    - All ModelTrainingBuild records
    - The ModelRepoConfig itself
    """
    service = RepositoryService(db)
    service.delete_repository(repo_id)


@router.get("/{repo_id}/import-progress")
def get_import_progress(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get detailed import progress for a repository.

    Returns breakdown by ModelImportBuild status:
    - pending: Queued for fetch
    - fetched: Fetched from CI API
    - ingesting: Clone/worktree/logs in progress
    - ingested: Ready for feature extraction
    - failed: Import failed
    """
    service = RepositoryService(db)
    return service.get_import_progress(repo_id)


@router.get("/{repo_id}/import-progress/failed")
def get_failed_import_builds(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get failed import builds with error details.

    Returns list of builds that failed during ingestion with:
    - ingestion_error: General error message
    - resource_errors: Per-resource error messages (git_history, git_worktree, build_logs)
    """
    service = RepositoryService(db)
    return service.get_failed_import_builds(repo_id, limit)


@router.post("/{repo_id}/sync-run")
def trigger_sync(
    repo_id: str,
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_REPOS)),
):
    """Trigger a manual sync for the repository (Admin only)."""
    user_id = str(_admin["_id"])
    service = RepositoryService(db)
    return service.trigger_sync(repo_id, user_id)


@router.post("/{repo_id}/reprocess-failed")
def trigger_reprocess_failed(
    repo_id: str,
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_REPOS)),
):
    """Reprocess only failed builds in the repository (Admin only)."""
    service = RepositoryService(db)
    return service.trigger_reprocess_failed(repo_id)


@router.post("/{repo_id}/reingest-failed")
def trigger_reingest_failed(
    repo_id: str,
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_REPOS)),
):
    """Retry failed ingestion builds in the repository (Admin only)."""
    service = RepositoryService(db)
    return service.trigger_reingest_failed(repo_id)


@router.post("/{repo_id}/start-processing")
def start_processing(
    repo_id: str,
    db: Database = Depends(get_db),
    _admin: dict = Depends(RequirePermission(Permission.MANAGE_REPOS)),
):
    """
    Start feature extraction phase (Admin only).

    Phase 2 of the two-phase pipeline.
    Allowed when status is: ingested, imported, or partial.
    Uses checkpoint to process only new builds since last processing.
    """
    service = RepositoryService(db)
    return service.start_processing(repo_id)


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
    extraction_status: str | None = Query(
        default=None,
        description="Filter by extraction status: pending, completed, failed, partial, not_started",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List builds for a repository.

    Returns RawBuildRun data with optional ModelTrainingBuild enrichment.
    Builds appear immediately after ingestion; extraction_status shows processing state.
    """
    service = ModelBuildService(db)
    return service.get_builds_by_repo(repo_id, skip, limit, q, extraction_status)


@router.get(
    "/{repo_id}/import-builds",
    response_model=ImportBuildListResponse,
    response_model_by_alias=False,
)
def get_import_builds(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(
        default=None, description="Search query (commit SHA, build ID)"
    ),
    status: str | None = Query(
        default=None,
        description="Filter by ingestion status: pending, fetched, ingesting, ingested, failed",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List import/ingestion builds for a repository.

    Shows ModelImportBuild data with resource status breakdown.
    For the Ingestion phase - shows what resources have been fetched/failed.
    """
    service = ModelBuildService(db)
    return service.get_import_builds(repo_id, skip, limit, q, status)


@router.get(
    "/{repo_id}/training-builds",
    response_model=TrainingBuildListResponse,
    response_model_by_alias=False,
)
def get_training_builds(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(
        default=None, description="Search query (build number, commit SHA)"
    ),
    extraction_status: str | None = Query(
        default=None,
        description="Filter by extraction status: pending, completed, failed, partial",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List training/processing builds for a repository.

    Shows ModelTrainingBuild data with extraction and prediction info.
    For the Processing phase - shows feature extraction and prediction results.
    """
    service = ModelBuildService(db)
    return service.get_training_builds(repo_id, skip, limit, q, extraction_status)


@router.get(
    "/{repo_id}/builds/unified",
    response_model=UnifiedBuildListResponse,
    response_model_by_alias=False,
)
def get_unified_builds(
    repo_id: str = Path(..., description="Repository id (Mongo ObjectId)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(
        default=None, description="Search query (build number, commit SHA)"
    ),
    phase: str | None = Query(
        default=None,
        description="Filter by phase: ingestion, processing, prediction",
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get unified builds combining ingestion and processing data.

    Returns all builds with status from all pipeline phases:
    - Ingestion status (resource collection)
    - Extraction status (feature extraction)
    - Prediction status (ML prediction results)

    Use phase filter to focus on specific phase.
    """
    model_build_service = ModelBuildService(db)
    return model_build_service.get_unified_builds(repo_id, skip, limit, q, phase)


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
    service = ModelBuildService(db)
    build = service.get_build_detail(build_id)
    if not build:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Build not found")
    return build


@router.get("/{repo_id}/export/preview")
def get_export_preview(
    repo_id: str = Path(..., description="Repository id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Preview exportable data with sample rows and available features."""
    service = RepositoryService(db)
    return service.get_export_preview(repo_id, current_user)


@router.get("/{repo_id}/export")
def export_builds_stream(
    repo_id: str = Path(..., description="Repository id"),
    format: str = Query(default="csv", description="Export format: csv or json"),
    features: str | None = Query(
        default=None, description="Comma-separated feature names"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream export builds as CSV.

    For small datasets. For large datasets (>1000 rows), use async export.
    """
    from fastapi.responses import StreamingResponse

    service = RepositoryService(db)
    feature_list = features.split(",") if features else None

    # Enforce CSV format
    format = "csv"

    content = service.export_builds_stream(
        repo_id=repo_id,
        format=format,
        features=feature_list,
    )

    from datetime import datetime

    media_type = "text/csv"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"builds_{repo_id}_{timestamp}.csv"

    return StreamingResponse(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{repo_id}/export/async")
def create_async_export(
    repo_id: str = Path(..., description="Repository id"),
    format: str = Query(default="csv", description="Export format: csv or json"),
    features: str | None = Query(
        default=None, description="Comma-separated feature names"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create background export job for large datasets.

    Returns job ID for tracking progress via GET /repos/export/jobs/{job_id}
    """
    service = RepositoryService(db)
    feature_list = features.split(",") if features else None

    # Enforce CSV format
    format = "csv"

    return service.create_export_job(
        repo_id=repo_id,
        user_id=str(current_user["_id"]),
        format=format,
        features=feature_list,
    )


@router.get("/{repo_id}/export/jobs")
def list_repo_export_jobs(
    repo_id: str = Path(..., description="Repository id"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List export jobs for a repository."""
    service = RepositoryService(db)
    return service.list_export_jobs(repo_id, limit)


@router.get("/export/jobs/{job_id}")
def get_export_job_status(
    job_id: str = Path(..., description="Export job id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get status of an export job."""
    service = RepositoryService(db)
    return service.get_export_job(job_id)


@router.get("/export/jobs/{job_id}/download")
def download_export_file(
    job_id: str = Path(..., description="Export job id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download completed export file."""
    from pathlib import Path as FilePath

    from fastapi.responses import FileResponse

    service = RepositoryService(db)
    user_id = str(current_user["_id"])
    file_path = service.get_export_download_path(job_id, user_id)

    path = FilePath(file_path)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/octet-stream",
    )
