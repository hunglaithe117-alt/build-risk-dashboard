"""Dataset API - manage uploaded CSV projects for enrichment."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path as PathParam, Query, UploadFile, status
from fastapi.responses import FileResponse
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
    DatasetTemplateListResponse,
    DatasetUpdateRequest,
    EnrichmentStartRequest,
    EnrichmentStartResponse,
    EnrichmentStatusResponse,
    EnrichmentValidateResponse,
    EnrichmentJobResponse,
)
from app.middleware.auth import get_current_user
from app.services.dataset_service import DatasetService
from app.services.dataset_template_service import DatasetTemplateService
from app.entities.enrichment_job import EnrichmentJob
from app.repositories.enrichment_job import EnrichmentJobRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.tasks.enrichment import enrich_dataset_task

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get(
    "/templates",
    response_model=DatasetTemplateListResponse,
    response_model_by_alias=False,
)
def list_dataset_templates(
    db: Database = Depends(get_db),
    _current_user: dict = Depends(get_current_user),
):
    service = DatasetTemplateService(db)
    return service.list_templates()


@router.get("/", response_model=DatasetListResponse, response_model_by_alias=False)
def list_datasets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search by name, file, or tag"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List datasets for the signed-in user."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.list_datasets(user_id, skip=skip, limit=limit, q=q)


@router.post(
    "/", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED, response_model_by_alias=False
)
def create_dataset(
    payload: DatasetCreateRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a dataset record (metadata only)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.create_dataset(user_id, payload)


@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    tags: list[str] = Form(default=[]),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Upload a CSV dataset and persist metadata."""
    user_id = str(current_user["_id"])
    upload_fobj = file.file
    try:
        upload_fobj.seek(0)
    except Exception:
        pass

    service = DatasetService(db)
    return service.create_from_upload(
        user_id=user_id,
        filename=file.filename,
        upload_file=upload_fobj,
        name=name,
        description=description,
        tags=tags,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def get_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get dataset details."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.get_dataset(dataset_id, user_id)


@router.patch(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def update_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    payload: DatasetUpdateRequest = ...,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update mappings, tags, or feature selections for a dataset."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.update_dataset(dataset_id, user_id, payload)


@router.post(
    "/{dataset_id}/apply-template/{template_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def apply_template_to_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    template_id: str = PathParam(..., description="Dataset template id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Apply a dataset template to a dataset, updating selected features."""
    user_id = str(current_user["_id"])
    service = DatasetTemplateService(db)
    return service.apply_template(dataset_id, template_id, user_id)


# ============================================================================
# ENRICHMENT ENDPOINTS
# ============================================================================


@router.post(
    "/{dataset_id}/validate",
    response_model=EnrichmentValidateResponse,
    response_model_by_alias=False,
)
def validate_for_enrichment(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Validate dataset for enrichment.
    
    Checks:
    - Required field mappings are complete
    - Which repositories exist in the system
    - Which repos will need to be auto-imported
    """
    import csv
    
    user_id = str(current_user["_id"])
    dataset_repo = DatasetRepository(db)
    repo_repo = ImportedRepositoryRepository(db)
    
    dataset = dataset_repo.find_by_id(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    if dataset.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check mapping
    mapping = dataset.get("mapped_fields", {})
    required_fields = ["build_id", "repo_name"]
    missing_mappings = [f for f in required_fields if not mapping.get(f)]
    mapping_complete = len(missing_mappings) == 0
    
    errors = []
    if not mapping_complete:
        errors.append(f"Missing required mappings: {', '.join(missing_mappings)}")
    
    # Read CSV to check repos
    repos_found = []
    repos_missing = []
    repos_invalid = []
    total_rows = 0
    
    file_path = dataset.get("file_path")
    if file_path and Path(file_path).exists():
        repo_name_col = mapping.get("repo_name")
        if repo_name_col:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                seen_repos = set()
                for row in reader:
                    total_rows += 1
                    repo_name = row.get(repo_name_col, "").strip()
                    if repo_name and repo_name not in seen_repos:
                        seen_repos.add(repo_name)
                        # Check if valid format
                        if "/" not in repo_name:
                            repos_invalid.append(repo_name)
                        else:
                            # Check if exists
                            if repo_repo.find_by_full_name(repo_name):
                                repos_found.append(repo_name)
                            else:
                                repos_missing.append(repo_name)
    
    return EnrichmentValidateResponse(
        valid=mapping_complete and len(repos_invalid) == 0,
        total_rows=total_rows,
        enrichable_rows=total_rows,  # All rows can potentially be enriched
        repos_found=repos_found,
        repos_missing=repos_missing,
        repos_invalid=repos_invalid,
        mapping_complete=mapping_complete,
        missing_mappings=missing_mappings,
        errors=errors,
    )


@router.post(
    "/{dataset_id}/enrich",
    response_model=EnrichmentStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_enrichment(
    dataset_id: str = PathParam(..., description="Dataset id"),
    payload: EnrichmentStartRequest = ...,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Start dataset enrichment job.
    
    This is an async operation. Use the returned job_id to:
    - Poll /enrich/status for progress
    - Connect to WebSocket for real-time updates
    """
    user_id = str(current_user["_id"])
    job_repo = EnrichmentJobRepository(db)
    dataset_repo = DatasetRepository(db)
    
    # Check dataset exists
    dataset = dataset_repo.find_by_id(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Check for existing active job
    active_job = job_repo.find_active_by_dataset(dataset_id)
    if active_job:
        raise HTTPException(
            status_code=409,
            detail=f"Enrichment already in progress (job_id: {str(active_job.id)})"
        )
    
    # Create job
    job = EnrichmentJob(
        dataset_id=dataset_id,
        user_id=user_id,
        selected_features=payload.selected_features,
        status="pending",
    )
    job = job_repo.create(job)
    
    # Start Celery task
    enrich_dataset_task.delay(
        job_id=str(job.id),
        dataset_id=dataset_id,
        user_id=user_id,
        selected_features=payload.selected_features,
        auto_import_repos=payload.auto_import_repos,
        skip_existing=payload.skip_existing,
    )
    
    return EnrichmentStartResponse(
        job_id=str(job.id),
        status="pending",
        message="Enrichment job started",
        websocket_url=f"/ws/enrichment/{str(job.id)}",
    )


@router.get(
    "/{dataset_id}/enrich/status",
    response_model=EnrichmentStatusResponse,
)
def get_enrichment_status(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current enrichment job status."""
    job_repo = EnrichmentJobRepository(db)
    
    # Find most recent job for dataset
    jobs = job_repo.find_by_dataset(dataset_id)
    if not jobs:
        raise HTTPException(status_code=404, detail="No enrichment job found")
    
    job = jobs[0]  # Most recent
    
    return EnrichmentStatusResponse(
        job_id=str(job.id),
        status=job.status,
        progress_percent=job.progress_percent,
        processed_rows=job.processed_rows,
        total_rows=job.total_rows,
        enriched_rows=job.enriched_rows,
        failed_rows=job.failed_rows,
        repos_auto_imported=job.repos_auto_imported,
        error=job.error,
        output_file=job.output_file,
    )


@router.post(
    "/{dataset_id}/enrich/cancel",
    response_model=EnrichmentJobResponse,
)
def cancel_enrichment(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel running enrichment job."""
    from celery.result import AsyncResult
    from app.celery_app import celery_app
    
    job_repo = EnrichmentJobRepository(db)
    
    active_job = job_repo.find_active_by_dataset(dataset_id)
    if not active_job:
        raise HTTPException(status_code=404, detail="No active enrichment job")
    
    # Revoke Celery task
    if active_job.celery_task_id:
        AsyncResult(active_job.celery_task_id, app=celery_app).revoke(terminate=True)
    
    # Mark as cancelled
    job_repo.mark_cancelled(str(active_job.id))
    active_job.status = "cancelled"
    
    return EnrichmentJobResponse(
        id=str(active_job.id),
        dataset_id=active_job.dataset_id,
        status="cancelled",
        total_rows=active_job.total_rows,
        processed_rows=active_job.processed_rows,
        enriched_rows=active_job.enriched_rows,
        failed_rows=active_job.failed_rows,
        selected_features=active_job.selected_features,
    )


@router.get(
    "/{dataset_id}/download",
)
def download_enriched_dataset(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download enriched dataset as CSV."""
    job_repo = EnrichmentJobRepository(db)
    
    # Find completed job
    jobs = job_repo.find_by_dataset(dataset_id)
    completed_job = next((j for j in jobs if j.status == "completed" and j.output_file), None)
    
    if not completed_job:
        raise HTTPException(status_code=404, detail="No completed enrichment found")
    
    output_path = Path(completed_job.output_file)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Enriched file not found")
    
    return FileResponse(
        path=output_path,
        media_type="text/csv",
        filename=output_path.name,
    )


@router.get(
    "/{dataset_id}/enrich/jobs",
    response_model=list[EnrichmentJobResponse],
)
def list_enrichment_jobs(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all enrichment jobs for a dataset."""
    job_repo = EnrichmentJobRepository(db)
    jobs = job_repo.find_by_dataset(dataset_id)
    
    return [
        EnrichmentJobResponse(
            id=str(job.id),
            dataset_id=job.dataset_id,
            status=job.status,
            total_rows=job.total_rows,
            processed_rows=job.processed_rows,
            enriched_rows=job.enriched_rows,
            failed_rows=job.failed_rows,
            progress_percent=job.progress_percent,
            selected_features=job.selected_features,
            repos_auto_imported=job.repos_auto_imported,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error=job.error,
            output_file=job.output_file,
            created_at=job.created_at,
        )
        for job in jobs
    ]

