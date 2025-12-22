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
from app.services.export_service import ExportService, ExportSource

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
        self._repo = DatasetVersionRepository(db)
        self._dataset_service = DatasetService(db)
        self._export_service = ExportService(db)
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
        if not version or version.dataset_id != dataset_id:
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
    ) -> ExportResult:
        """Export version data from DB in specified format."""
        import os
        import tempfile

        dataset = self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        # Validate format
        if format not in ("csv", "json", "parquet"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {format}. Use csv, json, or parquet.",
            )

        # Get count to check if we have data
        count = self._export_service.estimate_row_count(
            source=ExportSource.ENRICHMENT_BUILDS,
            dataset_id=dataset_id,
            version_id=version_id,
        )

        if count == 0:
            raise HTTPException(
                status_code=404,
                detail="No enriched builds found for this version",
            )

        filename = f"enriched_{dataset.name}_v{version.version_number}.{format}"

        if format == "parquet":
            # Parquet requires random access for writing metadata.
            # For large datasets (>50k rows), we write to a temp file and stream it back
            # to avoid OOM issues with keeping the whole file in RAM.
            PARQUET_MEMORY_LIMIT = 50000

            if count > PARQUET_MEMORY_LIMIT:
                fd, path = tempfile.mkstemp(suffix=".parquet")
                os.close(fd)

                try:
                    self._generate_parquet_content(
                        dataset_id,
                        version_id,
                        features or version.selected_features,
                        output_path=path,
                    )
                    return ExportResult(
                        content_generator=self._file_iterator(path, delete_after=True),
                        filename=filename,
                        media_type="application/octet-stream",
                    )
                except Exception:
                    # Cleanup if generation failed
                    if os.path.exists(path):
                        os.unlink(path)
                    raise

            # Small enough for memory
            content = self._generate_parquet_content(
                dataset_id, version_id, features or version.selected_features
            )
            return ExportResult(
                content_generator=iter([content]),  # type: ignore
                filename=filename,
                media_type="application/octet-stream",
            )

        # CSV/JSON can be streamed directly
        content_generator = self._export_service.export_enrichment_version(
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

    def _file_iterator(
        self, file_path: str, chunk_size: int = 64 * 1024, delete_after: bool = False
    ) -> Generator[bytes, None, None]:
        """Yield file content in chunks and optionally delete file when done."""
        import os

        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        finally:
            if delete_after and os.path.exists(file_path):
                os.unlink(file_path)

    def _generate_parquet_content(
        self,
        dataset_id: str,
        version_id: str,
        features: List[str],
        output_path: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Generate Parquet content.

        If output_path is provided, writes to file and returns None.
        If output_path is None, writes to memory and returns bytes.
        """
        import io

        import pyarrow as pa
        import pyarrow.parquet as pq
        from bson import ObjectId

        # Get enriched builds from repository (iterator)
        builds = self._enrichment_build_repo.get_enriched_for_export(
            dataset_id=ObjectId(dataset_id),
            version_id=ObjectId(version_id),
        )

        # Use file path if provided, otherwise memory buffer
        sink = output_path if output_path else io.BytesIO()

        writer = None
        batch_size = 10000
        current_batch = []

        for build in builds:
            # Create dict for current row
            row = {f: build.features.get(f) for f in features}
            current_batch.append(row)

            if len(current_batch) >= batch_size:
                table = pa.Table.from_pylist(current_batch)

                # Initialize writer with schema from first batch
                if writer is None:
                    writer = pq.ParquetWriter(sink, table.schema, compression="snappy")

                # Ensure subsequent batches match the schema
                if table.schema != writer.schema:
                    # Attempt to cast to original schema (handles null -> type transitions)
                    # Note: This might fail if types are completely incompatible,
                    # but it's better than crashing on schema mismatch.
                    try:
                        table = table.cast(writer.schema)
                    except Exception:
                        # Fallback: let specific write fail if incompatible
                        pass

                writer.write_table(table)
                current_batch = []

        # Write remaining items
        if current_batch:
            table = pa.Table.from_pylist(current_batch)
            if writer is None:
                writer = pq.ParquetWriter(sink, table.schema, compression="snappy")
            else:
                if table.schema != writer.schema:
                    try:
                        table = table.cast(writer.schema)
                    except Exception:
                        pass
            writer.write_table(table)

        if writer:
            writer.close()

        if output_path is None:
            # If memory buffer, return bytes
            sink.seek(0)  # type: ignore
            return sink.getvalue()  # type: ignore

        return None

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
        """Delete a version and its enrichment builds. Permission validated at API layer."""
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status in (VersionStatus.PENDING, VersionStatus.PROCESSING):
            self._revoke_task(version.task_id)

        # Delete associated enrichment builds
        deleted = self._enrichment_build_repo.delete_by_version(version_id)
        logger.info(f"Deleted {deleted} enrichment builds for version {version_id}")

        self._repo.delete(version_id)
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

    def get_version_data(
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

        from app.repositories.raw_repository import RawRepositoryRepository

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        # Get paginated data
        skip = (page - 1) * page_size

        items, total_count = self._enrichment_build_repo.list_by_version(
            dataset_version_id=ObjectId(version_id), skip=skip, limit=page_size
        )

        # Batch lookup repo names
        raw_repo_repo = RawRepositoryRepository(self._repo.db)
        repo_id_set = {build.raw_repo_id for build in items}
        repo_map = {}
        for repo_id in repo_id_set:
            repo = raw_repo_repo.find_by_id(str(repo_id))
            if repo:
                repo_map[str(repo_id)] = repo.full_name

        # Build response with overview info
        builds = []
        expected_feature_count = len(version.selected_features)
        for build in items:
            builds.append(
                {
                    "id": str(build.id),
                    "raw_build_run_id": str(build.raw_build_run_id),
                    "repo_full_name": repo_map.get(str(build.raw_repo_id), "Unknown"),
                    "extraction_status": (
                        build.extraction_status.value
                        if hasattr(build.extraction_status, "value")
                        else build.extraction_status
                    ),
                    "feature_count": build.feature_count,
                    "expected_feature_count": expected_feature_count,
                    "skipped_features": build.skipped_features,
                    "missing_resources": build.missing_resources,
                    "enriched_at": (build.enriched_at.isoformat() if build.enriched_at else None),
                    "features": build.features,
                }
            )

        column_stats = {}
        if include_stats:
            column_stats = self._calculate_column_stats(
                dataset_id, version_id, version.selected_features
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
            "builds": builds,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
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

        from app.repositories.sonar_commit_scan import SonarCommitScanRepository
        from app.repositories.trivy_commit_scan import TrivyCommitScanRepository

        version_oid = ObjectId(version_id)

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

            task = start_trivy_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=scan.repo_full_name,
                raw_repo_id=str(scan.raw_repo_id),
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

            task = start_sonar_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=scan.repo_full_name,
                raw_repo_id=str(scan.raw_repo_id),
                component_key=scan.component_key,
            )

            return {"status": "dispatched", "task_id": task.id, "tool": "sonarqube"}

        else:
            raise HTTPException(status_code=400, detail=f"Invalid tool type: {tool_type}")
