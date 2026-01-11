"""Build Sources API - CSV upload and validation for training data sources."""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.database.mongo import get_database
from app.dtos.build_source import (
    BuildSourceListResponse,
    BuildSourceResponse,
    BuildSourceUpdate,
    SourceBuildResponse,
    SourceRepoStatsResponse,
)
from app.entities.build_source import BuildSource
from app.middleware.auth import get_current_user
from app.repositories.build_source import BuildSourceRepository
from app.repositories.source_build import SourceBuildRepository
from app.repositories.source_repo_stats import SourceRepoStatsRepository
from app.services.build_source_service import BuildSourceService

router = APIRouter(prefix="/build-sources", tags=["Build Sources"])


def get_build_source_service() -> BuildSourceService:
    """Factory for BuildSourceService."""
    db = get_database()
    return BuildSourceService(
        build_source_repo=BuildSourceRepository(db),
        source_build_repo=SourceBuildRepository(db),
        source_repo_stats_repo=SourceRepoStatsRepository(db),
    )


def to_response(source: BuildSource) -> BuildSourceResponse:
    """Convert entity to response DTO."""
    return BuildSourceResponse(
        id=str(source.id),
        name=source.name,
        description=source.description,
        file_name=source.file_name,
        rows=source.rows,
        size_bytes=source.size_bytes,
        columns=source.columns,
        mapped_fields=source.mapped_fields,
        preview=source.preview,
        ci_provider=source.ci_provider.value if source.ci_provider else None,
        validation_status=source.validation_status,
        validation_progress=source.validation_progress,
        validation_stats=source.validation_stats,
        validation_error=source.validation_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
        validation_started_at=source.validation_started_at,
        validation_completed_at=source.validation_completed_at,
        setup_step=source.setup_step,
    )


@router.post("", response_model=BuildSourceResponse)
async def upload_build_source(
    file: Annotated[UploadFile, File(...)],
    name: Annotated[str, Form()],
    description: Annotated[Optional[str], Form()] = None,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Upload a CSV file to create a new build source."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        source = await service.upload_csv(
            file=file,
            name=name,
            description=description,
            user_id=user.get("sub"),
        )
        return to_response(source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=BuildSourceListResponse)
def list_build_sources(
    skip: int = 0,
    limit: int = 20,
    q: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """List build sources for the current user."""
    sources, total = service.list_by_user(
        user_id=user.get("sub", ""),
        skip=skip,
        limit=limit,
        q=q,
    )
    return BuildSourceListResponse(
        items=[to_response(s) for s in sources],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{source_id}", response_model=BuildSourceResponse)
def get_build_source(
    source_id: str,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Get a specific build source."""
    source = service.get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Build source not found")
    return to_response(source)


@router.patch("/{source_id}", response_model=BuildSourceResponse)
def update_build_source(
    source_id: str,
    update: BuildSourceUpdate,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Update a build source (name, description, mappings)."""
    source = service.update(
        source_id=source_id,
        name=update.name,
        description=update.description,
        mapped_fields=(
            update.mapped_fields.model_dump() if update.mapped_fields else None
        ),
        ci_provider=update.ci_provider,
    )
    if not source:
        raise HTTPException(status_code=404, detail="Build source not found")
    return to_response(source)


@router.delete("/{source_id}")
def delete_build_source(
    source_id: str,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Delete a build source and all related data."""
    success = service.delete(source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Build source not found")
    return {"status": "deleted"}


@router.post("/{source_id}/validate")
def start_validation(
    source_id: str,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Start validation for a build source."""
    source = service.get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Build source not found")

    # Check if validation is already running
    if source.validation_status.value == "validating":
        raise HTTPException(status_code=400, detail="Validation already in progress")

    # Queue the validation task
    from app.tasks.source_validation import validate_build_source_task

    task = validate_build_source_task.delay(source_id)

    # Update source with task ID
    service.start_validation(source_id, task.id)

    return {"status": "started", "task_id": task.id}


@router.get("/{source_id}/repos", response_model=list[SourceRepoStatsResponse])
def get_source_repos(
    source_id: str,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Get repository stats for a source."""
    stats = service.get_repo_stats(source_id)
    return [
        SourceRepoStatsResponse(
            id=str(s.id),
            source_id=str(s.source_id),
            raw_repo_id=str(s.raw_repo_id),
            full_name=s.full_name,
            ci_provider=s.ci_provider.value if s.ci_provider else "github_actions",
            builds_total=s.builds_total,
            builds_found=s.builds_found,
            builds_not_found=s.builds_not_found,
            builds_filtered=s.builds_filtered,
            is_valid=s.is_valid,
            validation_error=s.validation_error,
        )
        for s in stats
    ]


@router.get("/{source_id}/builds", response_model=list[SourceBuildResponse])
def get_source_builds(
    source_id: str,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(get_current_user),
    service: BuildSourceService = Depends(get_build_source_service),
):
    """Get builds for a source with optional status filter."""
    builds = service.get_builds(source_id, status=status, skip=skip, limit=limit)
    return [
        SourceBuildResponse(
            id=str(b.id),
            source_id=str(b.source_id),
            build_id_from_source=b.build_id_from_source,
            repo_name_from_source=b.repo_name_from_source,
            status=b.status.value if hasattr(b.status, "value") else b.status,
            validation_error=b.validation_error,
            validated_at=b.validated_at,
            raw_repo_id=str(b.raw_repo_id) if b.raw_repo_id else None,
            raw_run_id=str(b.raw_run_id) if b.raw_run_id else None,
        )
        for b in builds
    ]
