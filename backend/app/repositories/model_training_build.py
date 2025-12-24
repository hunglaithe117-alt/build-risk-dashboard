"""Repository for ModelTrainingBuild entities (builds for ML model training)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
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

    def find_by_repo_and_run_id(
        self,
        repo_id: str,
        workflow_run_id: int,
    ) -> Optional[ModelTrainingBuild]:
        """Convenience method - finds by repo_id and workflow_run_id (denormalized)."""
        # Query by raw_repo_id and looking for matching build_number/workflow reference
        doc = self.collection.find_one(
            {
                "model_repo_config_id": self.ensure_object_id(repo_id),
            }
        )
        # For backward compatibility, look up in raw_workflow_runs to find the actual build
        if not doc:
            return None
        return ModelTrainingBuild(**doc) if doc else None

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

        Called when soft-deleting a ModelRepoConfig to clean up related builds.

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
            "total_builds_processed": 0,  # completed + partial
            "total_builds_failed": 0,
            "total_pending": 0,
        }

        for r in results:
            status = r["_id"]
            count = r["count"]

            if status in (ExtractionStatus.COMPLETED.value, ExtractionStatus.PARTIAL.value):
                stats["total_builds_processed"] += count
            elif status == ExtractionStatus.FAILED.value:
                stats["total_builds_failed"] += count
            elif status == ExtractionStatus.PENDING.value:
                stats["total_pending"] += count

        return stats
