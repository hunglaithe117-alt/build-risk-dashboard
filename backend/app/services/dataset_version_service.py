import logging
from dataclasses import dataclass
from typing import Generator, List, Optional

from fastapi import HTTPException
from pymongo.database import Database

from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.entities.dataset import DatasetProject
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
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
        self._db = db
        self._repo = DatasetVersionRepository(db)
        self._dataset_service = DatasetService(db)
        self._export_service = ExportService(db)
        self._enrichment_build_repo = DatasetEnrichmentBuildRepository(db)

    def _verify_dataset_access(self, dataset_id: str, user_id: str) -> DatasetProject:
        """Verify user has access to dataset. Raises HTTPException if not found."""
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
        self, dataset_id: str, user_id: str, limit: int = 50
    ) -> List[DatasetVersion]:
        """List all versions for a dataset."""
        self._verify_dataset_access(dataset_id, user_id)
        return self._repo.find_by_dataset(dataset_id, limit=limit)

    def get_version(
        self, dataset_id: str, version_id: str, user_id: str
    ) -> DatasetVersion:
        """Get a specific version."""
        self._verify_dataset_access(dataset_id, user_id)
        return self._get_version(dataset_id, version_id)

    def create_version(
        self,
        dataset_id: str,
        user_id: str,
        selected_features: List[str],
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DatasetVersion:
        """Create a new version and start enrichment task."""
        dataset = self._verify_dataset_access(dataset_id, user_id)

        if dataset.validation_status != "completed":
            raise HTTPException(
                status_code=400,
                detail="Dataset validation must be completed before creating versions",
            )

        active_version = self._repo.find_active_by_dataset(dataset_id)
        if active_version:
            raise HTTPException(
                status_code=400,
                detail=f"Version v{active_version.version_number} is still processing. "
                "Wait for it to complete or cancel it.",
            )

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

        from app.tasks.version_enrichment import start_enrichment

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
            # Parquet requires writing to file first
            content = self._generate_parquet_content(
                dataset_id, version_id, features or version.selected_features
            )
            return ExportResult(
                content_generator=iter([content]),
                filename=filename,
                media_type="application/octet-stream",
            )

        # CSV/JSON can be streamed
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

    def _generate_parquet_content(
        self,
        dataset_id: str,
        version_id: str,
        features: List[str],
    ) -> bytes:
        """Generate Parquet content as bytes."""
        import io
        import pandas as pd

        query = {
            "dataset_id": self._db.enrichment_builds.database.client.ObjectId(
                dataset_id
            ),
            "version_id": self._db.enrichment_builds.database.client.ObjectId(
                version_id
            ),
        }

        from bson import ObjectId

        query = {
            "dataset_id": ObjectId(dataset_id),
            "version_id": ObjectId(version_id),
        }

        cursor = self._db.enrichment_builds.find(query)

        rows = []
        for doc in cursor:
            row = {"build_id": doc.get("build_id_from_csv")}
            feature_dict = doc.get("features", {})
            for f in features:
                row[f] = feature_dict.get(f)
            rows.append(row)

        df = pd.DataFrame(rows)

        buffer = io.BytesIO()
        df.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        buffer.seek(0)

        return buffer.getvalue()

    def get_export_preview(
        self, dataset_id: str, version_id: str, user_id: str
    ) -> dict:
        """Get preview of exportable data."""
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        return self._export_service.get_enrichment_preview(
            dataset_id=dataset_id,
            version_id=version_id,
            limit=10,
        )

    def delete_version(self, dataset_id: str, version_id: str, user_id: str) -> None:
        """Delete a version and its enrichment builds."""
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status in (VersionStatus.PENDING, VersionStatus.PROCESSING):
            self._revoke_task(version.task_id)

        # Delete associated enrichment builds
        deleted = self._enrichment_build_repo.delete_by_version(version_id)
        logger.info(f"Deleted {deleted} enrichment builds for version {version_id}")

        self._repo.delete(version_id)
        logger.info(f"Deleted version {version_id} for dataset {dataset_id}")

    def cancel_version(
        self, dataset_id: str, version_id: str, user_id: str
    ) -> DatasetVersion:
        """Cancel a processing version."""
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

        logger.info(f"Cancelled version {version_id}")
        return version

    def get_version_data(
        self,
        dataset_id: str,
        version_id: str,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Get paginated version data with column statistics."""
        from bson import ObjectId

        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        query = {
            "dataset_id": ObjectId(dataset_id),
            "version_id": ObjectId(version_id),
        }

        # Get total count
        total_count = self._db.enrichment_builds.count_documents(query)

        # Get paginated data
        skip = (page - 1) * page_size
        cursor = (
            self._db.enrichment_builds.find(query)
            .sort("created_at", 1)
            .skip(skip)
            .limit(page_size)
        )

        # Format rows
        rows = []
        for doc in cursor:
            row = {
                "build_id": doc.get("build_id_from_csv"),
                "extraction_status": doc.get("extraction_status"),
            }
            feature_dict = doc.get("features", {})
            for f in version.selected_features:
                row[f] = feature_dict.get(f)
            rows.append(row)

        # Calculate column statistics (only on first page for performance)
        column_stats = {}
        if page == 1:
            column_stats = self._calculate_column_stats(
                dataset_id, version_id, version.selected_features
            )

        return {
            "version": {
                "id": str(version.id),
                "name": version.name,
                "version_number": version.version_number,
                "status": (
                    version.status.value
                    if hasattr(version.status, "value")
                    else version.status
                ),
                "total_rows": version.total_rows,
                "enriched_rows": version.enriched_rows,
                "failed_rows": version.failed_rows,
                "selected_features": version.selected_features,
                "created_at": (
                    version.created_at.isoformat() if version.created_at else None
                ),
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

        query = {
            "dataset_id": ObjectId(dataset_id),
            "version_id": ObjectId(version_id),
        }

        # Build aggregation pipeline for stats
        stats = {}
        total_docs = self._db.enrichment_builds.count_documents(query)

        if total_docs == 0:
            return stats

        for feature in features:
            feature_path = f"features.{feature}"

            # Count non-null values
            non_null_count = self._db.enrichment_builds.count_documents(
                {
                    **query,
                    feature_path: {"$ne": None},
                }
            )

            missing_count = total_docs - non_null_count
            missing_rate = (missing_count / total_docs) * 100 if total_docs > 0 else 0

            # Get sample values for type detection
            sample = self._db.enrichment_builds.find_one(
                {**query, feature_path: {"$ne": None}}, {feature_path: 1}
            )

            value_type = "unknown"
            if sample:
                value = sample.get("features", {}).get(feature)
                if isinstance(value, bool):
                    value_type = "boolean"
                elif isinstance(value, (int, float)):
                    value_type = "numeric"
                elif isinstance(value, str):
                    value_type = "string"
                elif isinstance(value, list):
                    value_type = "array"

            stats[feature] = {
                "non_null": non_null_count,
                "missing": missing_count,
                "missing_rate": round(missing_rate, 1),
                "type": value_type,
            }

            # For numeric types, calculate min/max/avg
            if value_type == "numeric":
                agg_result = list(
                    self._db.enrichment_builds.aggregate(
                        [
                            {"$match": {**query, feature_path: {"$type": "number"}}},
                            {
                                "$group": {
                                    "_id": None,
                                    "min": {"$min": f"${feature_path}"},
                                    "max": {"$max": f"${feature_path}"},
                                    "avg": {"$avg": f"${feature_path}"},
                                }
                            },
                        ]
                    )
                )
                if agg_result:
                    stats[feature]["min"] = agg_result[0].get("min")
                    stats[feature]["max"] = agg_result[0].get("max")
                    stats[feature]["avg"] = round(agg_result[0].get("avg", 0), 2)

        return stats

    def _revoke_task(self, task_id: Optional[str]) -> None:
        """Revoke a Celery task if it exists."""
        if task_id:
            from app.celery_app import celery_app

            celery_app.control.revoke(task_id, terminate=True)
