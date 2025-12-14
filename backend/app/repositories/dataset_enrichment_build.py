"""Repository for DatasetEnrichmentBuild entities (builds for dataset enrichment)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.entities.enums import ExtractionStatus
from app.repositories.base import BaseRepository


class DatasetEnrichmentBuildRepository(BaseRepository[DatasetEnrichmentBuild]):
    """Repository for DatasetEnrichmentBuild entities (Dataset enrichment flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "dataset_enrichment_builds", DatasetEnrichmentBuild)

    def find_by_csv_build_id(
        self,
        dataset_id: ObjectId,
        build_id_from_csv: str,
    ) -> Optional[DatasetEnrichmentBuild]:
        """Find build by dataset and original CSV build ID."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "build_id_from_csv": build_id_from_csv,
            }
        )
        return DatasetEnrichmentBuild(**doc) if doc else None

    def find_by_workflow_run(
        self,
        dataset_id: ObjectId,
        raw_workflow_run_id: ObjectId,
    ) -> Optional[DatasetEnrichmentBuild]:
        """Find build by dataset and workflow run."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "raw_workflow_run_id": raw_workflow_run_id,
            }
        )
        return DatasetEnrichmentBuild(**doc) if doc else None

    def list_by_dataset(
        self,
        dataset_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ExtractionStatus] = None,
    ) -> tuple[List[DatasetEnrichmentBuild], int]:
        """List builds for a dataset with pagination."""
        query: Dict[str, Any] = {"dataset_id": dataset_id}
        if status:
            query["extraction_status"] = (
                status.value if hasattr(status, "value") else status
            )

        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("csv_row_index", 1).skip(skip).limit(limit)
        )
        items = [DatasetEnrichmentBuild(**doc) for doc in cursor]
        return items, total

    def list_by_version(
        self,
        dataset_version_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[DatasetEnrichmentBuild], int]:
        """List builds for a dataset version with pagination."""
        query = {"dataset_version_id": dataset_version_id}
        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("csv_row_index", 1).skip(skip).limit(limit)
        )
        items = [DatasetEnrichmentBuild(**doc) for doc in cursor]
        return items, total

    def update_extraction_status(
        self,
        build_id: ObjectId,
        status: ExtractionStatus,
        error: Optional[str] = None,
        is_missing_commit: bool = False,
    ) -> None:
        """Update extraction status for a build."""
        update: Dict[str, Any] = {
            "extraction_status": status.value if hasattr(status, "value") else status,
            "updated_at": datetime.utcnow(),
        }
        if error:
            update["extraction_error"] = error
        if is_missing_commit:
            update["is_missing_commit"] = True

        self.collection.update_one({"_id": build_id}, {"$set": update})

    def save_features(
        self,
        build_id: ObjectId,
        features: Dict[str, Any],
    ) -> None:
        """Save extracted features to a build."""
        self.collection.update_one(
            {"_id": build_id},
            {
                "$set": {
                    "features": features,
                    "feature_count": len(features),
                    "extraction_status": ExtractionStatus.COMPLETED.value,
                    "enriched_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    def count_by_dataset(
        self,
        dataset_id: ObjectId,
        status: Optional[ExtractionStatus] = None,
    ) -> int:
        """Count builds for a dataset, optionally filtered by status."""
        query: Dict[str, Any] = {"dataset_id": dataset_id}
        if status:
            query["extraction_status"] = (
                status.value if hasattr(status, "value") else status
            )
        return self.collection.count_documents(query)

    def get_enriched_for_export(
        self,
        dataset_id: ObjectId,
        version_id: Optional[ObjectId] = None,
    ) -> List[DatasetEnrichmentBuild]:
        """Get all enriched builds for export, sorted by CSV row index."""
        query: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }
        if version_id:
            query["dataset_version_id"] = version_id

        cursor = self.collection.find(query).sort("csv_row_index", 1)
        return [DatasetEnrichmentBuild(**doc) for doc in cursor]

    def delete_by_dataset(self, dataset_id: ObjectId) -> int:
        """Delete all builds for a dataset."""
        result = self.collection.delete_many({"dataset_id": dataset_id})
        return result.deleted_count
