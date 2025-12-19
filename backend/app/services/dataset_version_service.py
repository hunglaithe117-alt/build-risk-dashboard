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

    def _verify_dataset_access(
        self, dataset_id: str, user_id: str, role: str = "user"
    ) -> DatasetProject:
        """
        Verify dataset access based on role:
        - admin: full
        - guest: read-only
        - user: no access
        """
        dataset = self._dataset_service.get_dataset(dataset_id, user_id, role=role)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if role == "user":
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to access datasets.",
            )
        return dataset

    def _get_version(self, dataset_id: str, version_id: str) -> DatasetVersion:
        """Get version and verify it belongs to dataset. Raises HTTPException if not found."""
        version = self._repo.find_by_id(version_id)
        if not version or version.dataset_id != dataset_id:
            raise HTTPException(status_code=404, detail="Version not found")
        return version

    def list_versions(
        self, dataset_id: str, user_id: str, role: str = "user", limit: int = 50
    ) -> List[DatasetVersion]:
        """List all versions for a dataset."""
        self._verify_dataset_access(dataset_id, user_id, role=role)
        return self._repo.find_by_dataset(dataset_id, limit=limit)

    def get_version(
        self, dataset_id: str, version_id: str, user_id: str, role: str = "user"
    ) -> DatasetVersion:
        """Get a specific version."""
        self._verify_dataset_access(dataset_id, user_id, role=role)
        return self._get_version(dataset_id, version_id)

    def create_version(
        self,
        dataset_id: str,
        user_id: str,
        role: str,
        selected_features: List[str],
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DatasetVersion:
        """Create a new version and start enrichment task."""
        from datetime import datetime, timezone

        from app.core.redis import RedisLock, get_redis

        if role not in ("admin", "guest"):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to create dataset versions. Admins and guests can create versions.",
            )

        dataset = self._verify_dataset_access(dataset_id, user_id, role=role)

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
                            detail=f"Please wait {remaining} seconds before creating a new version. "
                            "Previous version is cleaning up.",
                        )
                except (ValueError, TypeError):
                    pass  # Invalid cooldown value, ignore

            version_number = self._repo.get_next_version_number(dataset_id)

            version = DatasetVersion(
                dataset_id=dataset_id,
                user_id=user_id,
                version_number=version_number,
                name=name or "",
                description=description,
                selected_features=selected_features,
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
        role: str = "user",
        format: str = "csv",
        features: Optional[List[str]] = None,
    ) -> ExportResult:
        """Export version data from DB in specified format."""
        import os
        import tempfile

        dataset = self._verify_dataset_access(dataset_id, user_id, role=role)
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

    def get_export_preview(
        self, dataset_id: str, version_id: str, user_id: str, role: str = "user"
    ) -> dict:
        """Get preview of exportable data."""
        self._verify_dataset_access(dataset_id, user_id, role=role)

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

    def delete_version(self, dataset_id: str, version_id: str, user_id: str, role: str) -> None:
        """Delete a version and its enrichment builds."""
        if role not in ("admin", "guest"):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete dataset versions. Admins and guests can delete versions.",
            )

        self._verify_dataset_access(dataset_id, user_id, role=role)
        version = self._get_version(dataset_id, version_id)

        if version.status in (VersionStatus.PENDING, VersionStatus.PROCESSING):
            self._revoke_task(version.task_id)

        # Delete associated enrichment builds
        deleted = self._enrichment_build_repo.delete_by_version(version_id)
        logger.info(f"Deleted {deleted} enrichment builds for version {version_id}")

        self._repo.delete(version_id)
        logger.info(f"Deleted version {version_id} for dataset {dataset_id}")

    def cancel_version(
        self, dataset_id: str, version_id: str, user_id: str, role: str
    ) -> DatasetVersion:
        """Cancel a processing version.

        Sets a cooldown period to allow ingestion tasks to cleanup before
        a new version can be created.
        """
        from datetime import datetime, timezone

        from app.core.redis import get_redis

        if role not in ("admin", "guest"):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to cancel dataset versions. Admins and guests can cancel versions.",
            )

        self._verify_dataset_access(dataset_id, user_id, role=role)
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
        role: str = "user",
        page: int = 1,
        page_size: int = 20,
        include_stats: bool = True,
    ) -> dict:
        """Get paginated version data with column statistics."""
        from bson import ObjectId

        self._verify_dataset_access(dataset_id, user_id, role=role)
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

        rows = []
        for build in items:
            feature_dict = build.features
            row = {f: feature_dict.get(f) for f in version.selected_features}
            rows.append(row)

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
            "data": {
                "rows": rows,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size,
            },
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
