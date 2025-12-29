"""Repository for ModelTrainingBuild entities (builds for ML model training)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.client_session import ClientSession

from app.entities.enums import ExtractionStatus
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.base import BaseRepository


class ModelTrainingBuildRepository(BaseRepository[ModelTrainingBuild]):
    """Repository for ModelTrainingBuild entities (Model training flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "model_training_builds", ModelTrainingBuild)

    def find_by_workflow_run(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_id: ObjectId,
    ) -> Optional[ModelTrainingBuild]:
        """Find build by repo and workflow run."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": raw_build_run_id,
            }
        )
        return ModelTrainingBuild(**doc) if doc else None

    def find_by_raw_build_run_id(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_id: ObjectId,
    ) -> Optional[ModelTrainingBuild]:
        """Find build by raw repo and raw build run."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": raw_build_run_id,
            }
        )
        return ModelTrainingBuild(**doc) if doc else None

    def upsert_or_get(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_id: ObjectId,
        model_import_build_id: ObjectId,
        model_repo_config_id: ObjectId,
        head_sha: str,
        build_number: int,
        build_created_at: datetime,
        extraction_status: ExtractionStatus,
    ) -> tuple[ModelTrainingBuild, bool]:
        """
        Atomic upsert by business key (raw_repo_id + raw_build_run_id).

        Uses atomic find_one_and_update for thread safety.
        Returns the document and a boolean indicating if it was newly created.
        """
        doc = self.collection.find_one_and_update(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": raw_build_run_id,
            },
            {
                "$setOnInsert": {
                    "raw_repo_id": raw_repo_id,
                    "raw_build_run_id": raw_build_run_id,
                    "model_import_build_id": model_import_build_id,
                    "model_repo_config_id": model_repo_config_id,
                    "head_sha": head_sha,
                    "build_number": build_number,
                    "build_created_at": build_created_at,
                    "extraction_status": extraction_status.value
                    if hasattr(extraction_status, "value")
                    else extraction_status,
                    "created_at": datetime.utcnow(),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        build = ModelTrainingBuild(**doc)
        # Check if it was newly created by comparing created_at
        was_created = (
            doc.get("created_at") is not None
            and (datetime.utcnow() - doc.get("created_at", datetime.utcnow())).total_seconds() < 2
        )
        return build, was_created

    def list_by_repo(
        self,
        repo_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[ModelTrainingBuild], int]:
        """Convenience method - list by model_repo_config_id (string)."""
        return self.find_by_config(
            self.ensure_object_id(repo_id), skip, limit if limit > 0 else 10000
        )

    def count_by_repo_id(self, repo_id: str | ObjectId) -> int:
        """Convenience method - count by model_repo_config_id (string)."""
        return self.count_by_config(self.ensure_object_id(repo_id))

    def find_by_status(
        self,
        repo_id: str,
        status: ExtractionStatus,
        limit: int = 1000,
    ) -> List[ModelTrainingBuild]:
        """Find builds by extraction status for a repo."""
        query = {
            "model_repo_config_id": self.ensure_object_id(repo_id),
            "extraction_status": status.value if hasattr(status, "value") else status,
        }
        cursor = self.collection.find(query).limit(limit)
        return [ModelTrainingBuild(**doc) for doc in cursor]

    def find_failed_builds(
        self,
        model_repo_config_id: ObjectId,
    ) -> List[ModelTrainingBuild]:
        """Find all FAILED builds for a repo config."""
        return self.find_many(
            {
                "model_repo_config_id": model_repo_config_id,
                "extraction_status": ExtractionStatus.FAILED.value,
            }
        )

    def find_by_config(
        self,
        model_repo_config_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[ModelTrainingBuild], int]:
        """List builds for a model repo config with pagination."""
        query = {"model_repo_config_id": model_repo_config_id}
        return self.paginate(query, sort=[("build_created_at", -1)], skip=skip, limit=limit)

    def find_by_repo(
        self,
        raw_repo_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[ModelTrainingBuild], int]:
        """List builds for a raw repository with pagination."""
        query = {"raw_repo_id": raw_repo_id}
        return self.paginate(query, sort=[("build_created_at", -1)], skip=skip, limit=limit)

    def find_existing_by_raw_build_run_ids(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_ids: List[ObjectId],
    ) -> Dict[str, "ModelTrainingBuild"]:
        """
        Batch query: Find existing builds by raw_build_run_ids.

        Returns a dict mapping raw_build_run_id (str) -> ModelTrainingBuild
        for efficient O(1) lookup.

        Args:
            raw_repo_id: RawRepository ObjectId
            raw_build_run_ids: List of RawBuildRun ObjectIds

        Returns:
            Dict mapping raw_build_run_id string to ModelTrainingBuild
        """
        if not raw_build_run_ids:
            return {}

        builds = self.find_many(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": {"$in": raw_build_run_ids},
            }
        )
        return {str(b.raw_build_run_id): b for b in builds}

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
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    def count_by_config(
        self,
        model_repo_config_id: ObjectId,
        status: Optional[ExtractionStatus] = None,
    ) -> int:
        """Count builds for a config, optionally filtered by status."""
        query: Dict[str, Any] = {"model_repo_config_id": model_repo_config_id}
        if status:
            query["extraction_status"] = status.value if hasattr(status, "value") else status
        return self.collection.count_documents(query)

    def get_for_training(
        self,
        model_repo_config_id: ObjectId,
        limit: Optional[int] = None,
    ) -> List[ModelTrainingBuild]:
        """Get builds ready for training (completed extraction, labeled)."""
        query = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
            "is_labeled": True,
        }
        cursor = self.collection.find(query).sort("build_created_at", -1)
        if limit:
            cursor = cursor.limit(limit)
        return [ModelTrainingBuild(**doc) for doc in cursor]

    def delete_by_repo_config(
        self, model_repo_config_id: ObjectId, session: "ClientSession | None" = None
    ) -> int:
        """
        Delete all builds associated with a model repo config.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            session: Optional MongoDB session for transaction support

        Returns:
            Number of documents deleted.
        """
        result = self.collection.delete_many(
            {"model_repo_config_id": model_repo_config_id}, session=session
        )
        return result.deleted_count

    def get_for_export(
        self,
        model_repo_config_id: ObjectId,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ):
        """
        Get cursor for streaming export of builds.

        Returns a cursor (not materialized list) for memory-efficient streaming.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            start_date: Optional filter by build_created_at >= start_date
            end_date: Optional filter by build_created_at <= end_date
            build_status: Optional filter by build status

        Returns:
            MongoDB cursor for iteration
        """
        query: Dict[str, Any] = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }

        if start_date or end_date:
            query["build_created_at"] = {}
            if start_date:
                query["build_created_at"]["$gte"] = start_date
            if end_date:
                query["build_created_at"]["$lte"] = end_date

        if build_status:
            query["build_status"] = build_status

        return self.collection.find(query).sort("build_created_at", 1).batch_size(100)

    def get_all_feature_keys(
        self,
        model_repo_config_id: ObjectId,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> set:
        """
        Get all unique feature keys from completed builds for consistent CSV columns.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            start_date: Optional filter
            end_date: Optional filter
            build_status: Optional filter

        Returns:
            Set of feature key names
        """
        query: Dict[str, Any] = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }

        if start_date or end_date:
            query["build_created_at"] = {}
            if start_date:
                query["build_created_at"]["$gte"] = start_date
            if end_date:
                query["build_created_at"]["$lte"] = end_date

        if build_status:
            query["build_status"] = build_status

        pipeline = [
            {"$match": query},
            {"$project": {"feature_keys": {"$objectToArray": "$features"}}},
            {"$unwind": {"path": "$feature_keys", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": None, "keys": {"$addToSet": "$feature_keys.k"}}},
        ]

        result = list(self.collection.aggregate(pipeline))
        if result:
            return set(result[0].get("keys", []))
        return set()

    def count_for_export(
        self,
        model_repo_config_id: ObjectId,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> int:
        """Count builds available for export."""
        query: Dict[str, Any] = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }

        if start_date or end_date:
            query["build_created_at"] = {}
            if start_date:
                query["build_created_at"]["$gte"] = start_date
            if end_date:
                query["build_created_at"]["$lte"] = end_date

        if build_status:
            query["build_status"] = build_status

        return self.collection.count_documents(query)

    def aggregate_stats_by_repo_config(
        self,
        model_repo_config_id: ObjectId,
    ) -> Dict[str, int]:
        """
        Aggregate build stats by extraction status for a repo config.
        Returns a dictionary with counts for 'completed', 'failed', 'pending', etc.
        """
        pipeline = [
            {"$match": {"model_repo_config_id": model_repo_config_id}},
            {"$group": {"_id": "$extraction_status", "count": {"$sum": 1}}},
        ]
        results = list(self.collection.aggregate(pipeline))

        stats = {
            "builds_processed": 0,  # completed + partial
            "builds_failed": 0,
            "total_pending": 0,
        }

        for r in results:
            status = r["_id"]
            count = r["count"]

            if status in (ExtractionStatus.COMPLETED.value, ExtractionStatus.PARTIAL.value):
                stats["builds_processed"] += count
            elif status == ExtractionStatus.FAILED.value:
                stats["builds_failed"] += count
            elif status == ExtractionStatus.PENDING.value:
                stats["total_pending"] += count

        return stats

    def find_builds_needing_prediction(
        self,
        model_repo_config_id: ObjectId,
        limit: int = 1000,
    ) -> List[ModelTrainingBuild]:
        """
        Find processed builds that need prediction.

        Returns builds where:
        - extraction_status is COMPLETED or PARTIAL
        - predicted_label is None (no prediction yet)
        - prediction_error is None (not failed)

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            limit: Maximum number of builds to return

        Returns:
            List of builds needing prediction
        """
        query = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": {
                "$in": [
                    ExtractionStatus.COMPLETED.value,
                    ExtractionStatus.PARTIAL.value,
                ]
            },
            "predicted_label": None,
            "prediction_error": None,
        }
        cursor = self.collection.find(query).limit(limit)
        return [ModelTrainingBuild(**doc) for doc in cursor]

    def find_builds_with_failed_predictions(
        self,
        model_repo_config_id: ObjectId,
        limit: int = 1000,
    ) -> List[ModelTrainingBuild]:
        """
        Find builds where prediction failed (has error but could be retried).

        Returns builds where:
        - extraction_status is COMPLETED or PARTIAL (features extracted)
        - prediction_error is NOT None (prediction failed)

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            limit: Maximum number of builds to return

        Returns:
            List of builds with failed predictions
        """
        query = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": {
                "$in": [
                    ExtractionStatus.COMPLETED.value,
                    ExtractionStatus.PARTIAL.value,
                ]
            },
            "prediction_error": {"$ne": None},
        }
        cursor = self.collection.find(query).limit(limit)
        return [ModelTrainingBuild(**doc) for doc in cursor]
