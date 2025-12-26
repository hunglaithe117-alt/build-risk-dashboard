import logging
from dataclasses import dataclass
from typing import Generator, List, Optional

from bson.objectid import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.entities.dataset import DatasetProject
from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.services.dataset_service import DatasetService
from app.services.normalization_service import NormalizationMethod, NormalizationService

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
        from datetime import datetime, timezone

        from app.core.redis import RedisLock, get_redis

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
                    "Wait for it to complete or cancel it.",
                )

            redis = get_redis()
            cooldown_key = f"version_cancelled:{dataset_id}"
            cooldown_until = redis.get(cooldown_key)
            if cooldown_until:
                try:
                    cooldown_ts = float(cooldown_until)
                    now_ts = datetime.now(timezone.utc).timestamp()
                    if now_ts < cooldown_ts:
                        remaining = int(cooldown_ts - now_ts)
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Please wait {remaining} seconds before creating a new version. "
                                "Previous version is cleaning up."
                            ),
                        )
                except (ValueError, TypeError):
                    pass  # Invalid cooldown value, ignore

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
                dataset_id=dataset_id,
                user_id=user_id,
                version_number=version_number,
                name=name or "",
                description=description,
                selected_features=selected_features,
                feature_configs=feature_configs or {},
                scan_metrics=normalized_scan_metrics,
                scan_config=normalized_scan_config,
                total_rows=dataset.rows or 0,
                status=VersionStatus.PENDING,
            )

            if not version.name:
                version.name = version.generate_default_name()

            version = self._repo.create(version)

            from app.tasks.enrichment_processing import start_enrichment

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
        normalization: str = "none",
    ) -> ExportResult:
        """Export version data from DB in specified format with optional normalization."""

        dataset = self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.COMPLETED:
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

        # Validate normalization method
        try:
            norm_method = NormalizationMethod(normalization)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid normalization: {normalization}. Use none/minmax/zscore.",
            ) from exc

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
            normalization=norm_method,
        )

        media_type = "text/csv" if format == "csv" else "application/json"

        return ExportResult(
            content_generator=content_generator,
            filename=filename,
            media_type=media_type,
        )

    def _stream_enrichment_export(
        self,
        dataset_id: str,
        version_id: str,
        format: str,
        features: Optional[List[str]] = None,
        normalization: NormalizationMethod = NormalizationMethod.NONE,
    ) -> Generator[str, None, None]:
        """Stream enrichment builds as CSV or JSON with optional normalization."""
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

        # Calculate normalization params if needed
        norm_params_map = None
        if normalization != NormalizationMethod.NONE:
            norm_params_map = self._calculate_normalization_params(
                dataset_id=dataset_id,
                version_id=version_id,
                features=features or all_feature_keys or [],
                method=normalization,
            )

        if format == "csv":
            return stream_csv(
                cursor, format_feature_row, features, all_feature_keys, norm_params_map
            )
        else:
            return stream_json(cursor, format_feature_row, features, norm_params_map)

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

        if version.status != VersionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        # Get row count
        total = self._enrichment_build_repo.count_by_query(
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
        self._verify_dataset_access(dataset_id, user_id)

        builds = self._enrichment_build_repo.get_enriched_for_export(
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
            limit=10,
        )

        total_rows = 0
        sample_rows = []
        all_features = set()

        for doc in builds:
            row = self._format_row(doc)
            sample_rows.append(row)
            all_features.update(row.keys())

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

        if version.status in (VersionStatus.PENDING, VersionStatus.PROCESSING):
            self._revoke_task(version.task_id)

        audit_log_repo = FeatureAuditLogRepository(self._db)

        # Use transaction for atomic deletion
        with get_transaction() as session:
            # 1. Delete associated FeatureAuditLogs
            audit_deleted = audit_log_repo.delete_by_version_id(version_id, session=session)
            logger.info(f"Deleted {audit_deleted} audit logs for version {version_id}")

            # 2. Delete associated enrichment builds
            deleted = self._enrichment_build_repo.delete_by_version(version_id, session=session)
            logger.info(f"Deleted {deleted} enrichment builds for version {version_id}")

            # 3. Delete the version
            self._repo.delete(version_id, session=session)
            logger.info(f"Deleted version {version_id} for dataset {dataset_id}")

    def cancel_version(self, dataset_id: str, version_id: str, user_id: str) -> DatasetVersion:
        """Cancel a processing version. Permission validated at API layer.

        Sets a cooldown period to allow ingestion tasks to cleanup before
        a new version can be created.
        """
        from datetime import datetime, timezone

        from app.core.redis import get_redis

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status not in (VersionStatus.PENDING, VersionStatus.PROCESSING):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel version with status: {version.status}",
            )

        self._revoke_task(version.task_id)
        self._repo.mark_cancelled(version_id)
        version.status = VersionStatus.CANCELLED

        cooldown_seconds = 10
        redis = get_redis()
        cooldown_key = f"version_cancelled:{dataset_id}"
        cooldown_until = datetime.now(timezone.utc).timestamp() + cooldown_seconds
        redis.set(cooldown_key, str(cooldown_until), ex=cooldown_seconds + 5)

        logger.info(f"Cancelled version {version_id}, cooldown set for {cooldown_seconds}s")
        return version

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

        if version.status != VersionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        column_stats = {}
        if include_stats:
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
                    "skipped_features": build.get("skipped_features", []),
                    "missing_resources": build.get("missing_resources", []),
                    "enriched_at": (
                        build["enriched_at"].isoformat() if build.get("enriched_at") else None
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
                "total_rows": version.total_rows,
                "enriched_rows": version.enriched_rows,
                "failed_rows": version.failed_rows,
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

    def _calculate_normalization_params(
        self,
        dataset_id: str,
        version_id: str,
        features: List[str],
        method: NormalizationMethod,
    ) -> dict:
        """Calculate normalization parameters for all features."""
        from typing import Dict

        if method == NormalizationMethod.NONE:
            return {}

        # Collect all values for each feature (from both features and scan_metrics)
        feature_values: Dict[str, list] = {f: [] for f in features}

        cursor = self._enrichment_build_repo.get_enriched_for_export(
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
        )

        for doc in cursor:
            # Merge features and scan_metrics
            feature_dict = doc.get("features", {})
            scan_metrics = doc.get("scan_metrics", {})
            merged = {**feature_dict, **scan_metrics}

            for feature_name in features:
                if feature_name in merged:
                    feature_values[feature_name].append(merged[feature_name])

        # Calculate params
        return NormalizationService.calculate_params_batch(feature_values, method)

    def _revoke_task(self, task_id: Optional[str]) -> None:
        """Revoke a Celery task if it exists."""
        if task_id:
            from app.celery_app import celery_app

            celery_app.control.revoke(task_id, terminate=True)

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

        from app.tasks.enrichment_processing import dispatch_version_scans

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
    ) -> dict:
        """
        Get detailed commit scan status for a version.

        Returns separate lists for Trivy and SonarQube scans.
        """
        self._verify_dataset_access(dataset_id, user_id)
        self._get_version(dataset_id, version_id)

        from app.repositories.sonar_commit_scan import SonarCommitScanRepository
        from app.repositories.trivy_commit_scan import TrivyCommitScanRepository

        trivy_repo = TrivyCommitScanRepository(self._repo.db)
        sonar_repo = SonarCommitScanRepository(self._repo.db)

        version_oid = ObjectId(version_id)

        trivy_scans = trivy_repo.find_by_version(version_oid)
        sonar_scans = sonar_repo.find_by_version(version_oid)

        return {
            "trivy": [
                {
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
                for s in trivy_scans
            ],
            "sonarqube": [
                {
                    "id": str(s.id),
                    "commit_sha": s.commit_sha,
                    "repo_full_name": s.repo_full_name,
                    "component_key": s.component_key,
                    "status": s.status.value,
                    "error_message": s.error_message,
                    "builds_affected": s.builds_affected,
                    "retry_count": s.retry_count,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in sonar_scans
            ],
        }

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

            from app.tasks.trivy import start_trivy_scan_for_version_commit

            # Lookup github_repo_id from RawRepository
            raw_repo = raw_repo_repo.find_by_id(str(scan.raw_repo_id))
            if not raw_repo:
                raise HTTPException(status_code=404, detail="Repository not found")

            task = start_trivy_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=scan.repo_full_name,
                raw_repo_id=str(scan.raw_repo_id),
                github_repo_id=raw_repo.github_repo_id,
                trivy_config=trivy_config,
                selected_metrics=selected_metrics,
            )

            return {"status": "dispatched", "task_id": task.id, "tool": "trivy"}

        elif tool_type == "sonarqube":
            sonar_repo = SonarCommitScanRepository(self._repo.db)
            scan = sonar_repo.find_by_version_and_commit(version_oid, commit_sha)

            if not scan:
                raise HTTPException(status_code=404, detail="SonarQube scan not found")

            # Increment retry count
            sonar_repo.increment_retry(scan.id)

            from app.tasks.sonar import start_sonar_scan_for_version_commit

            # Lookup github_repo_id from RawRepository
            raw_repo = raw_repo_repo.find_by_id(str(scan.raw_repo_id))
            if not raw_repo:
                raise HTTPException(status_code=404, detail="Repository not found")

            task = start_sonar_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=scan.repo_full_name,
                raw_repo_id=str(scan.raw_repo_id),
                github_repo_id=raw_repo.github_repo_id,
                component_key=scan.component_key,
            )

            return {"status": "dispatched", "task_id": task.id, "tool": "sonarqube"}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid tool type: {tool_type}")
