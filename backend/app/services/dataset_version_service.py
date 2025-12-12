import io
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
from fastapi import HTTPException
from pymongo.database import Database

from app.entities.dataset_version import DatasetVersion, VersionStatus
from app.entities.dataset import DatasetProject
from app.repositories.dataset_version import DatasetVersionRepository
from app.services.dataset_service import DatasetService


logger = logging.getLogger(__name__)


@dataclass
class CSVDownload:
    """Result of CSV generation for download."""

    content: str
    filename: str


class DatasetVersionService:
    """Service for managing dataset versions."""

    def __init__(self, db: Database):
        self._db = db
        self._repo = DatasetVersionRepository(db)
        self._dataset_service = DatasetService(db)

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

        from app.tasks.version_enrichment import enrich_version_task

        task = enrich_version_task.delay(str(version.id))
        self._repo.update_one(str(version.id), {"task_id": task.id})

        logger.info(
            f"Created version {version_number} for dataset {dataset_id} "
            f"with {len(selected_features)} features"
        )

        return version

    def download_as_csv(
        self, dataset_id: str, version_id: str, user_id: str
    ) -> CSVDownload:
        """Convert version's Parquet file to CSV for download."""
        dataset = self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status != VersionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Version is not completed. Status: {version.status}",
            )

        if not version.file_path or not os.path.exists(version.file_path):
            raise HTTPException(status_code=404, detail="Output file not found")

        try:
            df = pd.read_parquet(version.file_path)
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            filename = f"enriched_{dataset.name}_v{version.version_number}.csv"
            return CSVDownload(content=csv_buffer.getvalue(), filename=filename)
        except Exception as e:
            logger.error(f"Failed to convert Parquet to CSV: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate CSV file")

    def delete_version(self, dataset_id: str, version_id: str, user_id: str) -> None:
        """Delete a version and its output file."""
        self._verify_dataset_access(dataset_id, user_id)
        version = self._get_version(dataset_id, version_id)

        if version.status in (VersionStatus.PENDING, VersionStatus.PROCESSING):
            self._revoke_task(version.task_id)

        if version.file_path and os.path.exists(version.file_path):
            try:
                os.remove(version.file_path)
            except OSError as e:
                logger.warning(f"Failed to delete file {version.file_path}: {e}")

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

    def _revoke_task(self, task_id: Optional[str]) -> None:
        """Revoke a Celery task if it exists."""
        if task_id:
            from app.celery_app import celery_app

            celery_app.control.revoke(task_id, terminate=True)
