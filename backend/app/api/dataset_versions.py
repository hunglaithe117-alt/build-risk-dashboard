# ruff: noqa: B008
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from app.database.mongo import get_db
from app.dtos.dataset_version import (
    CreateVersionRequest,
    VersionListResponse,
    VersionResponse,
)
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.middleware.rbac import Permission, RequirePermission
from app.services.dataset_version_service import DatasetVersionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets/{dataset_id}/versions", tags=["Dataset Versions"])


def _to_response(version: DatasetVersion) -> VersionResponse:
    return VersionResponse(
        id=str(version.id),
        dataset_id=str(version.dataset_id),
        version_number=version.version_number,
        name=version.name,
        description=version.description,
        selected_features=version.selected_features,
        status=(
            version.status.value
            if isinstance(version.status, VersionStatus)
            else version.status
        ),
        scan_metrics=version.scan_metrics,
        builds_total=version.builds_total,
        builds_ingested=version.builds_ingested,
        builds_missing_resource=version.builds_missing_resource,
        builds_ingestion_failed=version.builds_ingestion_failed,
        builds_features_extracted=version.builds_features_extracted,
        builds_extraction_failed=version.builds_extraction_failed,
        progress_percent=version.progress_percent,
        started_at=version.started_at.isoformat() if version.started_at else None,
        completed_at=version.completed_at.isoformat() if version.completed_at else None,
        error_message=version.error_message,
        created_at=version.created_at.isoformat() if version.created_at else "",
    )


@router.get("", response_model=VersionListResponse)
async def list_versions(
    dataset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    service = DatasetVersionService(db)
    versions, total = service.list_versions(
        dataset_id, str(current_user["_id"]), skip=skip, limit=limit
    )
    return VersionListResponse(
        versions=[_to_response(v) for v in versions],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=VersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    dataset_id: str,
    request: CreateVersionRequest,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    service = DatasetVersionService(db)
    version = service.create_version(
        dataset_id=dataset_id,
        user_id=str(current_user["_id"]),
        selected_features=request.selected_features,
        feature_configs=request.feature_configs,
        scan_metrics=request.scan_metrics,
        scan_config=request.scan_config,
        name=request.name,
        description=request.description,
    )
    return _to_response(version)


@router.get("/{version_id}", response_model=VersionResponse)
async def get_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    service = DatasetVersionService(db)
    version = service.get_version(dataset_id, version_id, str(current_user["_id"]))
    return _to_response(version)


@router.get("/{version_id}/import-builds")
async def get_import_builds(
    dataset_id: str,
    version_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, ingesting, ingested, missing_resource",
    ),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    List import builds for a dataset version (Ingestion Phase).

    Shows DatasetImportBuild data with resource status breakdown.
    For the Ingestion phase - shows what resources have been fetched/failed.
    """
    service = DatasetVersionService(db)
    return service.get_import_builds(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        skip=skip,
        limit=limit,
        status_filter=status,
    )


@router.get("/{version_id}/enrichment-builds")
async def get_enrichment_builds(
    dataset_id: str,
    version_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    extraction_status: Optional[str] = Query(
        None,
        description="Filter by extraction status: pending, completed, failed, partial",
    ),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    List enrichment builds for a dataset version (Processing Phase).

    Shows DatasetEnrichmentBuild data with extraction status and features.
    For the Processing phase - shows feature extraction results.
    """
    service = DatasetVersionService(db)
    return service.get_enrichment_builds(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        skip=skip,
        limit=limit,
        extraction_status=extraction_status,
    )


@router.get("/{version_id}/export")
async def export_version(
    dataset_id: str,
    version_id: str,
    format: str = Query("csv", regex="^(csv|json)$"),
    features: Optional[List[str]] = Query(None),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.EXPORT_DATA)),
):
    """
    Export version data in CSV or JSON format.

    - **format**: Export format (csv or json)
    - **features**: Optional list of features to include (defaults to all selected features)
    """
    service = DatasetVersionService(db)
    result = service.export_version(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        format=format,
        features=features,
    )

    return StreamingResponse(
        result.content_generator,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/{version_id}/preview")
async def preview_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """Get preview of exportable data for a version."""
    service = DatasetVersionService(db)
    return service.get_export_preview(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.get("/{version_id}/data")
async def get_version_data(
    dataset_id: str,
    version_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get paginated version data with column statistics.

    Returns:
    - version: Metadata about the version
    - data: Paginated rows with features
    - column_stats: Statistics for each feature column (only on page 1)
    """
    service = DatasetVersionService(db)
    return await service.get_version_data(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        page=page,
        page_size=page_size,
    )


@router.delete("/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    service = DatasetVersionService(db)
    service.delete_version(dataset_id, version_id, str(current_user["_id"]))


@router.get("/{version_id}/builds/{build_id}")
async def get_build_detail(
    dataset_id: str,
    version_id: str,
    build_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get complete details for a single enriched build.

    Returns aggregated data from:
    - RawBuildRun: CI build metadata (branch, commit, status, etc.)
    - DatasetEnrichmentBuild: Extracted features and status
    - FeatureAuditLog: Extraction logs and node execution details
    """
    service = DatasetVersionService(db)
    return service.get_enrichment_build_detail(
        dataset_id=dataset_id,
        version_id=version_id,
        build_id=build_id,
        user_id=str(current_user["_id"]),
    )


@router.get("/{version_id}/scan-status")
async def get_scan_status(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get scan status summary for a version.

    Returns counts of builds with sonar/trivy features.
    """
    service = DatasetVersionService(db)
    return service.get_scan_status(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.get("/{version_id}/commit-scans")
async def get_commit_scans(
    dataset_id: str,
    version_id: str,
    tool_type: Optional[str] = Query(None, description="Tool type: trivy or sonarqube"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get detailed commit scan status for a version with pagination.

    Args:
        tool_type: Optional filter by tool (trivy or sonarqube). If not provided, returns both.
        skip: Number of items to skip
        limit: Maximum items to return
    """
    service = DatasetVersionService(db)
    return service.get_commit_scans(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        tool_type=tool_type,
        skip=skip,
        limit=limit,
    )


@router.get("/{version_id}/commit-scans/{commit_sha}")
async def get_commit_scan_detail(
    dataset_id: str,
    version_id: str,
    commit_sha: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get detailed scan metrics and related builds for a specific commit.

    Returns:
    - Trivy and SonarQube scan results with metrics
    - List of builds (with ci_run_id) that use this commit
    """
    service = DatasetVersionService(db)
    return service.get_commit_scan_detail(
        dataset_id=dataset_id,
        version_id=version_id,
        commit_sha=commit_sha,
        user_id=str(current_user["_id"]),
    )


@router.post("/{version_id}/commit-scans/{commit_sha}/retry")
async def retry_commit_scan(
    dataset_id: str,
    version_id: str,
    commit_sha: str,
    tool_type: str = Query(..., description="Tool type: trivy or sonarqube"),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.START_SCANS)),
):
    """
    Retry a specific commit scan for a tool (trivy or sonarqube).
    """
    service = DatasetVersionService(db)
    return service.retry_commit_scan(
        dataset_id=dataset_id,
        version_id=version_id,
        commit_sha=commit_sha,
        tool_type=tool_type,
        user_id=str(current_user["_id"]),
    )


# =========================================================================
# Processing Phase Control Endpoints
# =========================================================================


@router.post("/{version_id}/start-processing")
async def start_version_processing(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """
    Start processing phase after ingestion completes.

    Only allowed when version status is INGESTED.
    Dispatches sequential feature extraction for temporal feature support.
    """
    version_service = DatasetVersionService(db)
    return version_service.start_processing(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.post("/{version_id}/retry-ingestion")
async def retry_failed_ingestion(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """
    Retry failed ingestion builds.

    Resets MISSING_RESOURCE DatasetImportBuild records and re-triggers ingestion.
    Only allowed when status is INGESTED or FAILED.
    """
    version_service = DatasetVersionService(db)
    return version_service.retry_failed_ingestion(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


@router.post("/{version_id}/retry-processing")
async def retry_failed_processing(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """
    Retry failed processing (feature extraction) builds.

    Resets FAILED DatasetEnrichmentBuild records and re-dispatches extraction.
    """
    version_service = DatasetVersionService(db)
    return version_service.retry_failed_processing(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
    )


# =========================================================================
# Async Export Endpoints (for large datasets)
# =========================================================================


@router.post("/{version_id}/export/async")
async def create_export_job(
    dataset_id: str,
    version_id: str,
    format: str = Query("csv", regex="^(csv|json)$"),
    features: Optional[List[str]] = Query(None),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.EXPORT_DATA)),
):
    """Create an async export job for large datasets."""
    service = DatasetVersionService(db)
    return service.create_export_job(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        format=format,
        features=features,
    )


@router.get("/{version_id}/export/jobs")
async def list_export_jobs(
    dataset_id: str,
    version_id: str,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """List export jobs for a version."""
    service = DatasetVersionService(db)
    return service.list_export_jobs(
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=str(current_user["_id"]),
        limit=limit,
    )


@router.get("/export/jobs/{job_id}")
async def get_export_job_status(
    job_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """Get export job status."""
    service = DatasetVersionService(db)
    return service.get_export_job(
        job_id=job_id,
        user_id=str(current_user["_id"]),
    )


@router.get("/export/jobs/{job_id}/download")
async def download_export_file(
    job_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.EXPORT_DATA)),
):
    """Download completed export file."""
    from fastapi.responses import FileResponse

    service = DatasetVersionService(db)
    file_path = service.get_export_download_path(
        job_id=job_id,
        user_id=str(current_user["_id"]),
    )

    return FileResponse(
        file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream",
    )


# =========================================================================
# Quality Evaluation Endpoints
# =========================================================================


@router.post("/{version_id}/evaluate")
async def evaluate_version_quality(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.MANAGE_DATASETS)),
):
    """
    Start quality evaluation for a completed version.

    Calculates:
    - Completeness: % features non-null
    - Validity: % values within valid range
    - Consistency: % builds with all selected features
    - Coverage: % successfully enriched builds

    Quality Score = 0.4*completeness + 0.3*validity + 0.2*consistency + 0.1*coverage
    """
    from app.services.data_quality_service import DataQualityService

    quality_service = DataQualityService(db)
    report = quality_service.evaluate_version(
        dataset_id=dataset_id,
        version_id=version_id,
    )

    return {
        "report_id": str(report.id),
        "status": report.status,
        "message": (
            "Quality evaluation completed"
            if report.status == "completed"
            else f"Evaluation {report.status}"
        ),
        "quality_score": report.quality_score if report.status == "completed" else None,
    }


@router.get("/{version_id}/quality-report")
async def get_quality_report(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get the latest quality evaluation report for a version.

    Returns:
    - Overall quality score and breakdown
    - Per-feature metrics
    - Detected issues
    """
    from app.dtos.data_quality import (
        QualityIssueResponse,
        QualityMetricResponse,
        QualityReportResponse,
    )
    from app.services.data_quality_service import DataQualityService

    quality_service = DataQualityService(db)
    report = quality_service.get_report(dataset_id, version_id)

    if not report:
        return {
            "available": False,
            "message": "No quality report available for this version. Run evaluation first.",
        }

    # Convert to response format
    feature_metrics = [
        QualityMetricResponse(
            feature_name=m.feature_name,
            data_type=m.data_type,
            total_values=m.total_values,
            null_count=m.null_count,
            completeness_pct=m.completeness_pct,
            validity_pct=m.validity_pct,
            min_value=m.min_value,
            max_value=m.max_value,
            mean_value=m.mean_value,
            std_dev=m.std_dev,
            expected_range=m.expected_range,
            out_of_range_count=m.out_of_range_count,
            invalid_value_count=m.invalid_value_count,
            issues=m.issues,
        )
        for m in report.feature_metrics
    ]

    issues = [
        QualityIssueResponse(
            severity=i.severity if isinstance(i.severity, str) else i.severity.value,
            category=i.category,
            feature_name=i.feature_name,
            message=i.message,
            details=i.details,
        )
        for i in report.issues
    ]

    return QualityReportResponse(
        id=str(report.id),
        dataset_id=str(report.dataset_id),
        version_id=str(report.version_id),
        status=report.status if isinstance(report.status, str) else report.status.value,
        error_message=report.error_message,
        quality_score=report.quality_score,
        completeness_score=report.completeness_score,
        validity_score=report.validity_score,
        consistency_score=report.consistency_score,
        coverage_score=report.coverage_score,
        total_builds=report.total_builds,
        enriched_builds=report.enriched_builds,
        partial_builds=report.partial_builds,
        failed_builds=report.failed_builds,
        total_features=report.total_features,
        features_with_issues=report.features_with_issues,
        feature_metrics=feature_metrics,
        issues=issues,
        issue_counts=report.get_issue_count_by_severity(),
        started_at=report.started_at,
        completed_at=report.completed_at,
        created_at=report.created_at,
    )
