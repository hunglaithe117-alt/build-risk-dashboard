import logging
from dataclasses import dataclass
from typing import Generator, List, Optional

from bson.objectid import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.entities.dataset import DatasetProject
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_import_build import DatasetImportBuildRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Result of export generation for download."""

    content_generator: Generator[str, None, None]
    filename: str
    media_type: str


class DatasetVersionService:
    """Service for managing dataset versions."""

    def __init__(self, db: Database):
        self._db = db
        self._repo = DatasetVersionRepository(db)
        self._dataset_service = DatasetService(db)
        self._enrichment_build_repo = DatasetEnrichmentBuildRepository(db)
        self._import_build_repo = DatasetImportBuildRepository(db)

    def _verify_dataset_access(self, dataset_id: str, user_id: str) -> DatasetProject:
        """
        Verify dataset exists. Permission is validated at API layer.
        """
        dataset = self._dataset_service.get_dataset(dataset_id, user_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        return dataset

    def _get_version(self, dataset_id: str, version_id: str) -> DatasetVersion:
        """Get version and verify it belongs to dataset. Raises HTTPException if not found."""
        version = self._repo.find_by_id(version_id)
        if not version or str(version.dataset_id) != dataset_id:
            raise HTTPException(status_code=404, detail="Version not found")
        return version

    def list_versions(
        self, dataset_id: str, user_id: str, skip: int = 0, limit: int = 10
    ) -> tuple[List[DatasetVersion], int]:
        """List all versions for a dataset with pagination."""
        self._verify_dataset_access(dataset_id, user_id)
        return self._repo.find_by_dataset(dataset_id, skip=skip, limit=limit)

    def get_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersion:
        """Get a specific version."""
        self._verify_dataset_access(dataset_id, user_id)
        return self._get_version(dataset_id, version_id)

    def create_version(
        self,
        dataset_id: str,
        user_id: str,
        selected_features: List[str],
        feature_configs: Optional[dict] = None,
        scan_metrics: Optional[dict] = None,
        scan_config: Optional[dict] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DatasetVersion:
        """Create a new version and start enrichment task. Permission validated at API layer."""
        from app.core.redis import RedisLock

        dataset = self._verify_dataset_access(dataset_id, user_id)

        if dataset.validation_status != "completed":
            raise HTTPException(
                status_code=400,
                detail="Dataset validation must be completed before creating versions",
            )

        # Use Redis lock to prevent race conditions when creating versions
        lock_key = f"version_create:{dataset_id}"
        with RedisLock(lock_key, timeout=30, blocking_timeout=5):
            active_version = self._repo.find_active_by_dataset(dataset_id)
            if active_version:
                raise HTTPException(
                    status_code=400,
                    detail=f"Version v{active_version.version_number} is still processing. "
                    "Wait for it to complete.",
                )

            version_number = self._repo.get_next_version_number(dataset_id)

            # Normalize scan_metrics
            normalized_scan_metrics = {"sonarqube": [], "trivy": []}
            if scan_metrics:
                normalized_scan_metrics["sonarqube"] = scan_metrics.get("sonarqube", [])
                normalized_scan_metrics["trivy"] = scan_metrics.get("trivy", [])

            # Normalize scan_config
            normalized_scan_config = {"sonarqube": {}, "trivy": {}}
            if scan_config:
                normalized_scan_config["sonarqube"] = scan_config.get("sonarqube", {})
                normalized_scan_config["trivy"] = scan_config.get("trivy", {})

            version = DatasetVersion(
                _id=None,
                dataset_id=ObjectId(dataset_id),
                user_id=ObjectId(user_id),
                version_number=version_number,
                name=name or "",
                description=description,
                selected_features=selected_features,
                feature_configs=feature_configs or {},
                scan_metrics=normalized_scan_metrics,
                scan_config=normalized_scan_config,
                builds_total=dataset.rows or 0,
                status=VersionStatus.QUEUED,
            )

            if not version.name:
                version.name = version.generate_default_name()

            version = self._repo.create(version)

            from app.tasks.enrichment_ingestion import start_enrichment

            task = start_enrichment.delay(str(version.id))
            self._repo.update_one(str(version.id), {"task_id": task.id})

            logger.info(
                f"Created version {version_number} for dataset {dataset_id} "
                f"with {len(selected_features)} features"
            )

            return version

    def export_version(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
    ) -> ExportResult:
        """Export version data from DB in specified format."""

        dataset = self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.PROCESSED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        # Validate format (csv and json only)
        if format not in ("csv", "json"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {format}. Use csv or json.",
            )

        # Get count to check if we have data
        count = self._enrichment_build_repo.count(
            {
                "dataset_id": ObjectId(dataset_id),
                "dataset_version_id": ObjectId(version_id),
            }
        )

        if count == 0:
            raise HTTPException(
                status_code=404,
                detail="No enriched builds found for this version",
            )

        filename = f"enriched_{dataset.name}_v{version.version_number}.{format}"

        # CSV/JSON can be streamed directly
        content_generator = self._stream_enrichment_export(
            dataset_id=dataset_id,
            version_id=version_id,
            format=format,
            features=features or version.selected_features,
        )

        media_type = "text/csv" if format == "csv" else "application/json"

        return ExportResult(
            content_generator=content_generator,
            filename=filename,
            media_type=media_type,
        )

    def get_ingestion_progress(self, dataset_id: str, version_id: str, user_id: str) -> dict:
        """Get ingestion progress summary for a dataset version."""
        self._verify_dataset_access(dataset_id, user_id)
        self._get_version(dataset_id, version_id)

        import_repo = DatasetImportBuildRepository(self._db)
        status_counts = import_repo.count_by_status(version_id)
        total = sum(status_counts.values())
        resource_status = import_repo.get_resource_status_summary(version_id)

        return {
            "total": total,
            "status_counts": status_counts,
            "resource_status": resource_status,
        }

    def get_import_builds(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        status_filter: Optional[str] = None,
    ) -> dict:
        """
        List import builds for a dataset version (Ingestion Phase).

        Returns DatasetImportBuild records with resource status breakdown.
        """
        self._verify_dataset_access(dataset_id, user_id)
        self._get_version(dataset_id, version_id)

        import_repo = DatasetImportBuildRepository(self._db)
        builds, total = import_repo.list_by_version_with_details(
            version_id=ObjectId(version_id),
            skip=skip,
            limit=limit,
            status_filter=status_filter,
        )

        items = []
        for build in builds:
            items.append(
                {
                    "id": str(build.get("_id")),
                    "build_id": build.get("ci_run_id", ""),
                    "build_number": build.get("build_number"),
                    "commit_sha": build.get("commit_sha", ""),
                    "branch": build.get("branch", ""),
                    "conclusion": build.get("conclusion", "unknown"),
                    "created_at": (
                        build["created_at"].isoformat() if build.get("created_at") else None
                    ),
                    "web_url": build.get("web_url"),
                    "status": build.get("status", "pending"),
                    "ingested_at": (
                        build["ingested_at"].isoformat() if build.get("ingested_at") else None
                    ),
                    "resource_status": build.get("resource_status", {}),
                    "required_resources": build.get("required_resources", []),
                    # RawBuildRun fields for detailed view
                    "commit_message": build.get("commit_message"),
                    "commit_author": build.get("commit_author"),
                    "duration_seconds": build.get("duration_seconds"),
                    "started_at": (
                        build["started_at"].isoformat() if build.get("started_at") else None
                    ),
                    "completed_at": (
                        build["completed_at"].isoformat() if build.get("completed_at") else None
                    ),
                    "provider": build.get("provider"),
                    "logs_available": build.get("logs_available"),
                    "logs_expired": build.get("logs_expired"),
                    "ingestion_error": build.get("ingestion_error"),
                }
            )

        return {
            "items": items,
            "total": total,
            "page": (skip // limit) + 1,
            "size": limit,
        }

    def get_enrichment_builds(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        extraction_status: Optional[str] = None,
    ) -> dict:
        """
        List enrichment builds for a dataset version (Processing Phase).

        Returns DatasetEnrichmentBuild records with extraction status.
        """
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        builds, total = self._enrichment_build_repo.list_by_version_with_details(
            ObjectId(version_id),
            skip=skip,
            limit=limit,
        )

        expected_features = len(version.selected_features)
        items = []
        for build in builds:
            items.append(
                {
                    "id": str(build.get("_id")),
                    "raw_build_run_id": str(build.get("raw_build_run_id")),
                    "repo_full_name": build.get("repo_full_name", "Unknown"),
                    "web_url": build.get("web_url"),
                    "provider": build.get("provider"),
                    "extraction_status": build.get("extraction_status", "pending"),
                    "extraction_error": build.get("extraction_error"),
                    "feature_count": build.get("feature_count", 0),
                    "expected_feature_count": expected_features,
                    "missing_resources": build.get("missing_resources", []),
                    "created_at": (
                        build["created_at"].isoformat() if build.get("created_at") else None
                    ),
                }
            )

        return {
            "items": items,
            "total": total,
            "page": (skip // limit) + 1,
            "size": limit,
        }

    def _stream_enrichment_export(
        self,
        dataset_id: str,
        version_id: str,
        format: str,
        features: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        """Stream enrichment builds as CSV or JSON."""
        from app.utils.export_utils import format_feature_row, stream_csv, stream_json

        cursor = self._enrichment_build_repo.get_enriched_for_export(
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
        )

        # Get all feature keys for consistent CSV columns
        all_feature_keys = None
        if format == "csv" and not features:
            all_feature_keys = self._enrichment_build_repo.get_all_feature_keys(
                dataset_id=ObjectId(dataset_id),
                version_id=ObjectId(version_id),
            )

        if format == "csv":
            return stream_csv(cursor, format_feature_row, features, all_feature_keys)
        else:
            return stream_json(cursor, format_feature_row, features)

    # TODO: Implement incorrect handling for export dataset version
    # Async Export Methods (for large datasets)
    def create_export_job(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
    ) -> dict:
        """
        Create background export job for large datasets.

        Returns job ID for tracking progress.
        """
        from app.entities.export_job import ExportFormat, ExportJob, ExportStatus
        from app.repositories.export_job import ExportJobRepository
        from app.tasks.enrichment_processing import process_version_export_job

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.PROCESSED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        # Get row count
        total = self._enrichment_build_repo.count(
            {
                "dataset_id": ObjectId(dataset_id),
                "dataset_version_id": ObjectId(version_id),
            }
        )

        if total == 0:
            raise HTTPException(
                status_code=400,
                detail="No builds available for export",
            )

        job_repo = ExportJobRepository(self._db)

        job = ExportJob(
            _id=None,
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
            user_id=ObjectId(user_id),
            format=ExportFormat(format),
            status=ExportStatus.PENDING,
            features=features or version.selected_features,
            total_rows=total,
        )

        job = job_repo.create(job)

        # Queue background task
        process_version_export_job.delay(str(job.id))

        return {
            "job_id": str(job.id),
            "status": "pending",
            "total_rows": total,
        }

    def get_export_job(self, job_id: str, user_id: str) -> dict:
        """Get export job status."""
        from app.repositories.export_job import ExportJobRepository

        job_repo = ExportJobRepository(self._db)
        job = job_repo.find_by_id(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")

        return {
            "id": str(job.id),
            "status": job.status,
            "format": job.format,
            "total_rows": job.total_rows,
            "processed_rows": job.processed_rows,
            "progress": (job.processed_rows / job.total_rows * 100 if job.total_rows else 0),
            "file_path": job.file_path,
            "file_size": job.file_size,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def list_export_jobs(
        self, dataset_id: str, version_id: str, user_id: str, limit: int = 10
    ) -> list:
        """List export jobs for a version."""
        from app.repositories.export_job import ExportJobRepository

        self._verify_dataset_access(dataset_id, user_id)

        job_repo = ExportJobRepository(self._db)
        jobs = job_repo.list_by_version(version_id, limit)

        return [
            {
                "id": str(j.id),
                "status": j.status,
                "format": j.format,
                "total_rows": j.total_rows,
                "processed_rows": j.processed_rows,
                "file_size": j.file_size,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]

    def get_export_download_path(self, job_id: str, user_id: str) -> str:
        """Get file path for completed export job."""
        from app.repositories.export_job import ExportJobRepository

        job_repo = ExportJobRepository(self._db)
        job = job_repo.find_by_id(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")

        if str(job.user_id) != user_id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to download this export",
            )

        if job.status != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Export is not ready. Status: {job.status}",
            )

        if not job.file_path:
            raise HTTPException(status_code=404, detail="Export file not found")

        return job.file_path

    def get_export_preview(self, dataset_id: str, version_id: str, user_id: str) -> dict:
        """Get preview of exportable data."""
        from app.utils.export_utils import format_feature_row

        self._verify_dataset_access(dataset_id, user_id)

        builds = self._enrichment_build_repo.get_enriched_for_export(
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
            limit=10,
        )

        sample_rows = []
        all_features = set()

        for doc in builds:
            row = format_feature_row(doc)
            sample_rows.append(row)
            all_features.update(row.keys())

        # Get total count
        total_rows = self._enrichment_build_repo.count(
            {
                "dataset_id": ObjectId(dataset_id),
                "dataset_version_id": ObjectId(version_id),
                "extraction_status": "completed",
            }
        )

        return {
            "total_rows": total_rows,
            "sample_rows": sample_rows,
            "available_features": sorted(all_features),
            "feature_count": len(all_features),
        }

    def delete_version(self, dataset_id: str, version_id: str, user_id: str) -> None:
        """Delete a version and its enrichment builds atomically. Permission validated at API layer."""
        from app.database.mongo import get_transaction
        from app.repositories.feature_audit_log import FeatureAuditLogRepository

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status in (VersionStatus.QUEUED, VersionStatus.PROCESSING):
            self._revoke_task(version.task_id)

        audit_log_repo = FeatureAuditLogRepository(self._db)

        # Use transaction for atomic deletion
        with get_transaction() as session:
            # 1. Delete associated FeatureAuditLogs
            audit_deleted = audit_log_repo.delete_by_version_id(version_id, session=session)
            logger.info(f"Deleted {audit_deleted} audit logs for version {version_id}")

            # 2. Delete associated enrichment builds
            deleted_enrichment = self._enrichment_build_repo.delete_by_version(
                version_id, session=session
            )
            logger.info(f"Deleted {deleted_enrichment} enrichment builds for version {version_id}")

            # 3. Delete associated import builds
            deleted_import = self._import_build_repo.delete_by_version(version_id, session=session)
            logger.info(f"Deleted {deleted_import} import builds for version {version_id}")

            # 4. Delete the version
            self._repo.delete(version_id, session=session)
            logger.info(f"Deleted version {version_id} for dataset {dataset_id}")

    async def get_version_data(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        include_stats: bool = True,
    ) -> dict:
        """Get paginated version data with build overview and features."""
        from bson import ObjectId

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        # Allow viewing at any status - data is conditionally included based on phase
        is_processed = version.status == VersionStatus.PROCESSED

        column_stats = {}
        if include_stats and is_processed:
            column_stats = self._calculate_column_stats(
                dataset_id, version_id, version.selected_features
            )

        skip = (page - 1) * page_size

        # Use new repository method to get enriched data (with web_url and repo_name)
        builds_data, total = self._enrichment_build_repo.list_by_version_with_details(
            ObjectId(version_id), skip=skip, limit=page_size
        )

        formatted_builds = []
        expected_feature_count = len(version.selected_features)

        for build in builds_data:
            formatted_builds.append(
                {
                    "id": str(build.get("_id")),
                    "raw_build_run_id": str(build.get("raw_build_run_id")),
                    "repo_full_name": build.get("repo_full_name", "Unknown"),
                    "repo_url": build.get("repo_url"),
                    "provider": build.get("provider"),
                    "web_url": build.get("web_url"),
                    "extraction_status": build.get("extraction_status"),
                    "feature_count": build.get("feature_count", 0),
                    "expected_feature_count": expected_feature_count,
                    "missing_resources": build.get("missing_resources", []),
                    "created_at": (
                        build["created_at"].isoformat() if build.get("created_at") else None
                    ),
                    "features": build.get("features", {}),
                }
            )

        return {
            "version": {
                "id": str(version.id),
                "name": version.name,
                "version_number": version.version_number,
                "status": (
                    version.status.value if hasattr(version.status, "value") else version.status
                ),
                "builds_total": version.builds_total,
                "builds_ingested": version.builds_ingested,
                "builds_missing_resource": version.builds_missing_resource,
                "builds_processed": version.builds_processed,
                "builds_processing_failed": version.builds_processing_failed,
                "selected_features": version.selected_features,
                "created_at": (version.created_at.isoformat() if version.created_at else None),
                "completed_at": (
                    version.completed_at.isoformat() if version.completed_at else None
                ),
            },
            "builds": formatted_builds,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "column_stats": column_stats,
        }

    def _calculate_column_stats(
        self,
        dataset_id: str,
        version_id: str,
        features: List[str],
    ) -> dict:
        """Calculate statistics for each column."""
        from bson import ObjectId

        return self._enrichment_build_repo.get_feature_stats(
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
            features=features,
        )

    def _revoke_task(self, task_id: Optional[str]) -> None:
        """Revoke a Celery task if it exists."""
        if task_id:
            from app.celery_app import celery_app

            celery_app.control.revoke(task_id, terminate=True)

    def get_enrichment_build_detail(
        self,
        dataset_id: str,
        version_id: str,
        build_id: str,
        user_id: str,
    ) -> dict:
        """
        Get complete details for a single enriched build.

        Aggregates data from:
        - DatasetEnrichmentBuild: Build tracking and status
        - FeatureVector: Extracted features and scan metrics
        - RawBuildRun: CI build metadata
        - FeatureAuditLog: Extraction logs (optional)

        Args:
            build_id: ID of the DatasetEnrichmentBuild
        """
        from app.dtos.build import (
            AuditLogDetail,
            EnrichmentBuildDetail,
            EnrichmentBuildDetailResponse,
            NodeExecutionDetail,
            RawBuildRunDetail,
        )
        from app.repositories.feature_audit_log import FeatureAuditLogRepository
        from app.repositories.feature_vector import FeatureVectorRepository
        from app.repositories.raw_build_run import RawBuildRunRepository

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        # 1. Get enrichment build
        enrichment_build = self._enrichment_build_repo.find_by_id(build_id)
        if not enrichment_build:
            raise HTTPException(status_code=404, detail="Build not found")

        if str(enrichment_build.dataset_version_id) != version_id:
            raise HTTPException(
                status_code=404,
                detail="Build does not belong to this version",
            )

        # 2. Get feature vector (contains features and scan_metrics)
        feature_vector = None
        if enrichment_build.feature_vector_id:
            fv_repo = FeatureVectorRepository(self._db)
            feature_vector = fv_repo.find_by_id(str(enrichment_build.feature_vector_id))

        # 3. Get raw build run
        raw_run_repo = RawBuildRunRepository(self._db)
        raw_build_run = raw_run_repo.find_by_id(str(enrichment_build.raw_build_run_id))
        if not raw_build_run:
            raise HTTPException(status_code=404, detail="Raw build run not found")

        # 4. Get audit log (optional - may not exist)
        audit_log_repo = FeatureAuditLogRepository(self._db)
        audit_log = audit_log_repo.find_by_enrichment_build(build_id)

        # Build response DTOs
        raw_build_detail = RawBuildRunDetail(
            id=str(raw_build_run.id),
            ci_run_id=raw_build_run.ci_run_id,
            build_number=raw_build_run.build_number,
            repo_name=raw_build_run.repo_name,
            branch=raw_build_run.branch,
            commit_sha=raw_build_run.commit_sha,
            commit_message=raw_build_run.commit_message,
            commit_author=raw_build_run.commit_author,
            status=raw_build_run.status.value
            if hasattr(raw_build_run.status, "value")
            else str(raw_build_run.status),
            conclusion=raw_build_run.conclusion.value
            if hasattr(raw_build_run.conclusion, "value")
            else str(raw_build_run.conclusion),
            created_at=raw_build_run.created_at,
            started_at=raw_build_run.started_at,
            completed_at=raw_build_run.completed_at,
            duration_seconds=raw_build_run.duration_seconds,
            web_url=raw_build_run.web_url,
            provider=raw_build_run.provider.value
            if hasattr(raw_build_run.provider, "value")
            else str(raw_build_run.provider),
            logs_available=raw_build_run.logs_available,
            logs_expired=raw_build_run.logs_expired,
            is_bot_commit=raw_build_run.is_bot_commit,
        )

        # Get feature data from FeatureVector
        features = feature_vector.features if feature_vector else {}
        scan_metrics = feature_vector.scan_metrics if feature_vector else {}
        feature_count = feature_vector.feature_count if feature_vector else 0
        is_missing_commit = feature_vector.is_missing_commit if feature_vector else False
        missing_resources = feature_vector.missing_resources if feature_vector else []
        skipped_features = feature_vector.skipped_features if feature_vector else []

        enrichment_detail = EnrichmentBuildDetail(
            id=str(enrichment_build.id),
            extraction_status=enrichment_build.extraction_status.value
            if hasattr(enrichment_build.extraction_status, "value")
            else str(enrichment_build.extraction_status),
            extraction_error=enrichment_build.extraction_error,
            is_missing_commit=is_missing_commit,
            missing_resources=missing_resources,
            skipped_features=skipped_features,
            feature_count=feature_count,
            expected_feature_count=len(version.selected_features),
            features=features,
            scan_metrics=scan_metrics,
            enriched_at=enrichment_build.enriched_at,
        )

        audit_detail = None
        if audit_log:
            node_results = [
                NodeExecutionDetail(
                    node_name=n.node_name,
                    status=n.status.value if hasattr(n.status, "value") else str(n.status),
                    started_at=n.started_at,
                    completed_at=n.completed_at,
                    duration_ms=n.duration_ms,
                    features_extracted=n.features_extracted,
                    resources_used=n.resources_used,
                    error=n.error,
                    warning=n.warning,
                    skip_reason=n.skip_reason,
                    retry_count=n.retry_count,
                )
                for n in audit_log.node_results
            ]

            audit_detail = AuditLogDetail(
                id=str(audit_log.id),
                correlation_id=audit_log.correlation_id,
                started_at=audit_log.started_at,
                completed_at=audit_log.completed_at,
                duration_ms=audit_log.duration_ms,
                nodes_executed=audit_log.nodes_executed,
                nodes_succeeded=audit_log.nodes_succeeded,
                nodes_failed=audit_log.nodes_failed,
                nodes_skipped=audit_log.nodes_skipped,
                total_retries=audit_log.total_retries,
                feature_count=audit_log.feature_count,
                features_extracted=audit_log.features_extracted,
                errors=audit_log.errors,
                warnings=audit_log.warnings,
                node_results=node_results,
            )

        return EnrichmentBuildDetailResponse(
            raw_build_run=raw_build_detail,
            enrichment_build=enrichment_detail,
            audit_log=audit_detail,
        )

    def get_scan_status(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
    ) -> dict:
        """
        Get scan metrics status for a version.

        Returns counts of builds with sonar/trivy features.
        """
        self._verify_dataset_access(dataset_id, user_id)
        self._get_version(dataset_id, version_id)  # Verify exists

        from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository

        enrichment_repo = DatasetEnrichmentBuildRepository(self._repo.db)
        return enrichment_repo.get_scan_status_by_version(ObjectId(version_id))

    def retry_scans(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
    ) -> dict:
        """
        Retry scans for a version.

        Re-dispatches scan tasks for all unique commits in the version.
        """
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status not in ["completed", "failed"]:
            raise HTTPException(
                status_code=400,
                detail="Can only retry scans for completed or failed versions",
            )

        from app.tasks.enrichment_ingestion import dispatch_version_scans

        task = dispatch_version_scans.delay(version_id)

        return {
            "status": "dispatched",
            "task_id": task.id,
            "message": "Scan retry dispatched",
        }

    def get_commit_scans(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        tool_type: str = None,
        skip: int = 0,
        limit: int = 10,
    ) -> dict:
        """
        Get detailed commit scan status for a version with pagination.

        Args:
            tool_type: Optional filter by tool (trivy or sonarqube)
            skip: Number of items to skip
            limit: Maximum items to return
        """
        self._verify_dataset_access(dataset_id, user_id)
        self._get_version(dataset_id, version_id)

        from app.repositories.sonar_commit_scan import SonarCommitScanRepository
        from app.repositories.trivy_commit_scan import TrivyCommitScanRepository

        trivy_repo = TrivyCommitScanRepository(self._repo.db)
        sonar_repo = SonarCommitScanRepository(self._repo.db)

        version_oid = ObjectId(version_id)

        def format_scan(s, include_component_key=False):
            result = {
                "id": str(s.id),
                "commit_sha": s.commit_sha,
                "repo_full_name": s.repo_full_name,
                "status": s.status.value,
                "error_message": s.error_message,
                "builds_affected": s.builds_affected,
                "retry_count": s.retry_count,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            if include_component_key and hasattr(s, "component_key"):
                result["component_key"] = s.component_key
            return result

        result = {}

        if tool_type is None or tool_type == "trivy":
            trivy_scans, trivy_total = trivy_repo.list_by_version(version_oid, skip, limit)
            result["trivy"] = {
                "items": [format_scan(s) for s in trivy_scans],
                "total": trivy_total,
                "skip": skip,
                "limit": limit,
            }

        if tool_type is None or tool_type == "sonarqube":
            sonar_scans, sonar_total = sonar_repo.list_by_version(version_oid, skip, limit)
            result["sonarqube"] = {
                "items": [format_scan(s, include_component_key=True) for s in sonar_scans],
                "total": sonar_total,
                "skip": skip,
                "limit": limit,
            }

        return result

    def retry_commit_scan(
        self,
        dataset_id: str,
        version_id: str,
        commit_sha: str,
        tool_type: str,
        user_id: str,
        config_override: dict = None,
    ) -> dict:
        """
        Retry a specific commit scan for a tool.

        Args:
            tool_type: "trivy" or "sonarqube"
            config_override: Optional new config to use
        """
        self._verify_dataset_access(dataset_id, user_id)
        self._get_version(dataset_id, version_id)  # Verify exists

        from app.repositories.raw_repository import RawRepositoryRepository
        from app.repositories.sonar_commit_scan import SonarCommitScanRepository
        from app.repositories.trivy_commit_scan import TrivyCommitScanRepository

        version_oid = ObjectId(version_id)
        raw_repo_repo = RawRepositoryRepository(self._repo.db)

        if tool_type == "trivy":
            trivy_repo = TrivyCommitScanRepository(self._repo.db)
            scan = trivy_repo.find_by_version_and_commit(version_oid, commit_sha)

            if not scan:
                raise HTTPException(status_code=404, detail="Trivy scan not found")

            # Increment retry count
            trivy_repo.increment_retry(scan.id)

            # Use override config or existing
            trivy_config = config_override or scan.scan_config or {}
            selected_metrics = scan.selected_metrics or []

            from app.paths import get_trivy_config_path
            from app.tasks.trivy import start_trivy_scan_for_version_commit

            # Lookup github_repo_id from RawRepository
            raw_repo = raw_repo_repo.find_by_id(str(scan.raw_repo_id))
            if not raw_repo:
                raise HTTPException(status_code=404, detail="Repository not found")

            # Get config file path (may have been created during initial scan)
            trivy_config_path = get_trivy_config_path(version_id, raw_repo.github_repo_id)
            config_file_path = str(trivy_config_path) if trivy_config_path.exists() else None

            task = start_trivy_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=scan.repo_full_name,
                raw_repo_id=str(scan.raw_repo_id),
                github_repo_id=raw_repo.github_repo_id,
                trivy_config=trivy_config,
                selected_metrics=selected_metrics,
                config_file_path=config_file_path,
            )

            return {"status": "dispatched", "task_id": task.id, "tool": "trivy"}

        elif tool_type == "sonarqube":
            sonar_repo = SonarCommitScanRepository(self._repo.db)
            scan = sonar_repo.find_by_version_and_commit(version_oid, commit_sha)

            if not scan:
                raise HTTPException(status_code=404, detail="SonarQube scan not found")

            # Increment retry count
            sonar_repo.increment_retry(scan.id)

            from app.paths import get_sonarqube_config_path
            from app.tasks.sonar import start_sonar_scan_for_version_commit

            # Lookup github_repo_id from RawRepository
            raw_repo = raw_repo_repo.find_by_id(str(scan.raw_repo_id))
            if not raw_repo:
                raise HTTPException(status_code=404, detail="Repository not found")

            # Get config file path (may have been created during initial scan)
            sonar_config_path = get_sonarqube_config_path(version_id, raw_repo.github_repo_id)
            config_file_path = str(sonar_config_path) if sonar_config_path.exists() else None

            task = start_sonar_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=scan.repo_full_name,
                raw_repo_id=str(scan.raw_repo_id),
                github_repo_id=raw_repo.github_repo_id,
                component_key=scan.component_key,
                config_file_path=config_file_path,
            )

            return {"status": "dispatched", "task_id": task.id, "tool": "sonarqube"}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid tool type: {tool_type}")

    # =========================================================================
    # Processing Phase Control (matching model pipeline)
    # =========================================================================

    def start_processing(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
    ) -> dict:
        """
        Manually trigger processing phase after ingestion completes.

        Only allowed when status is INGESTING_COMPLETE or INGESTING_PARTIAL.
        """
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        valid_statuses = [
            VersionStatus.INGESTED,
        ]
        if version.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start processing: status is {version.status}. "
                f"Expected: {[s.value for s in valid_statuses]}",
            )

        from app.tasks.enrichment_processing import start_enrichment_processing

        task = start_enrichment_processing.delay(version_id)

        return {
            "status": "dispatched",
            "task_id": task.id,
            "message": "Processing phase started",
        }

    def retry_failed_ingestion(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
    ) -> dict:
        """
        Retry failed ingestion builds for a version.

        Resets FAILED DatasetImportBuild records and re-triggers ingestion.
        """
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        valid_statuses = [
            VersionStatus.INGESTED,
            VersionStatus.FAILED,
        ]
        if version.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry ingestion: status is {version.status}",
            )

        from app.tasks.enrichment_ingestion import reingest_failed_builds

        task = reingest_failed_builds.delay(version_id)

        return {
            "status": "dispatched",
            "task_id": task.id,
            "message": "Ingestion retry started for failed builds",
        }

    def retry_failed_processing(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
    ) -> dict:
        """
        Retry failed processing (enrichment) builds for a version.

        Resets FAILED DatasetEnrichmentBuild records and re-dispatches extraction.
        """
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        # Only allow retry if failed or processed
        valid_statuses = [
            VersionStatus.FAILED,
            VersionStatus.PROCESSED,  # Allow retry even on completed
        ]
        if version.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry processing: status is {version.status}",
            )

        from app.tasks.enrichment_processing import reprocess_failed_enrichment_builds

        task = reprocess_failed_enrichment_builds.delay(version_id)

        return {
            "status": "dispatched",
            "task_id": task.id,
            "message": "Processing retry started",
        }
