from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.client_session import ClientSession

from app.entities.enums import ExtractionStatus, FeatureVectorScope
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.base import BaseRepository


class ModelTrainingBuildRepository(BaseRepository[ModelTrainingBuild]):
    def __init__(self, db) -> None:
        super().__init__(db, "model_training_builds", ModelTrainingBuild)

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

        Also ensures a FeatureVector exists for this build (linked by raw_repo + raw_run).
        Uses atomic find_one_and_update for thread safety.
        Returns the document and a boolean indicating if it was newly created.
        """
        # 1. Ensure FeatureVector exists (Atomic Upsert)
        feature_vectors = self.db["feature_vectors"]
        now = datetime.utcnow()

        fv_doc = feature_vectors.find_one_and_update(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": raw_build_run_id,
                "scope": FeatureVectorScope.MODEL.value,
                "config_id": model_repo_config_id,
            },
            {
                "$setOnInsert": {
                    "raw_repo_id": raw_repo_id,
                    "raw_build_run_id": raw_build_run_id,
                    "scope": FeatureVectorScope.MODEL.value,
                    "config_id": model_repo_config_id,
                    "dag_version": "1.0",
                    "computed_at": now,
                    "created_at": now,
                    "updated_at": now,
                    "extraction_status": "pending",
                    "features": {},
                    "feature_count": 0,
                    "scan_metrics": {},
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        fv_id = fv_doc["_id"]

        # 2. Upsert ModelTrainingBuild with FV link
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
                    "feature_vector_id": fv_id,  # Link to FeatureVector
                    "extraction_status": (
                        extraction_status.value
                        if hasattr(extraction_status, "value")
                        else extraction_status
                    ),
                    "created_at": now,
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

    def find_builds_for_prediction(
        self,
        model_repo_config_id: ObjectId,
    ) -> List[ModelTrainingBuild]:
        """
        Find builds ready for prediction (extracted but not predicted).

        Returns builds where:
        - extraction_status is 'completed' or 'partial'
        - predicted_label is None (not predicted yet)
        - prediction_error is None (not failed)
        """
        return self.find_many(
            {
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
        limit: Optional[int] = None,
    ):
        """
        Get cursor for streaming export of builds with features from FeatureVector.

        Uses $lookup aggregation to join with feature_vectors collection.
        Returns a cursor (not materialized list) for memory-efficient streaming.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            start_date: Optional filter by build_created_at >= start_date
            end_date: Optional filter by build_created_at <= end_date
            build_status: Optional filter by build status
            limit: Optional limit for preview

        Returns:
            MongoDB aggregation cursor for iteration
        """
        match_query: Dict[str, Any] = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": {
                "$in": [
                    ExtractionStatus.COMPLETED.value,
                    ExtractionStatus.PARTIAL.value,
                ]
            },
        }

        if start_date or end_date:
            match_query["build_created_at"] = {}
            if start_date:
                match_query["build_created_at"]["$gte"] = start_date
            if end_date:
                match_query["build_created_at"]["$lte"] = end_date

        if build_status:
            match_query["build_status"] = build_status

        pipeline = [
            {"$match": match_query},
            {"$sort": {"build_created_at": 1}},
            # Join with feature_vectors to get features
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "feature_vector",
                }
            },
            # Unwind to get single feature_vector document
            {
                "$unwind": {
                    "path": "$feature_vector",
                    "preserveNullAndEmptyArrays": True,
                }
            },
            # Add features from feature_vector and prediction fields from training build
            {
                "$addFields": {
                    "features": {"$ifNull": ["$feature_vector.features", {}]},
                    "feature_count": {"$ifNull": ["$feature_vector.feature_count", 0]},
                    "scan_metrics": {"$ifNull": ["$feature_vector.scan_metrics", {}]},
                }
            },
            # Project final fields including predictions
            {
                "$project": {
                    "feature_vector": 0,  # Remove temp lookup field
                    # Keep all other fields including:
                    # - features, feature_count, scan_metrics (from feature_vector)
                    # - predicted_label, prediction_confidence, uncertainty
                    # - ground_truth, head_sha, build_number, build_created_at (metadata)
                }
            },
        ]

        if limit:
            pipeline.append({"$limit": limit})

        return self.collection.aggregate(pipeline, batchSize=100)

    def get_all_feature_keys(
        self,
        model_repo_config_id: ObjectId,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> set:
        """
        Get all unique feature keys from completed builds for consistent CSV columns.

        Joins with feature_vectors collection to get feature keys.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            start_date: Optional filter
            end_date: Optional filter
            build_status: Optional filter

        Returns:
            Set of feature key names
        """
        match_query: Dict[str, Any] = {
            "model_repo_config_id": model_repo_config_id,
            "extraction_status": {
                "$in": [
                    ExtractionStatus.COMPLETED.value,
                    ExtractionStatus.PARTIAL.value,
                ]
            },
        }

        if start_date or end_date:
            match_query["build_created_at"] = {}
            if start_date:
                match_query["build_created_at"]["$gte"] = start_date
            if end_date:
                match_query["build_created_at"]["$lte"] = end_date

        if build_status:
            match_query["build_status"] = build_status

        pipeline = [
            {"$match": match_query},
            # Join with feature_vectors
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "feature_vector",
                }
            },
            {
                "$unwind": {
                    "path": "$feature_vector",
                    "preserveNullAndEmptyArrays": False,
                }
            },
            # Extract feature keys from feature_vector.features
            {"$project": {"feature_keys": {"$objectToArray": "$feature_vector.features"}}},
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
            "extraction_status": {
                "$in": [
                    ExtractionStatus.COMPLETED.value,
                    ExtractionStatus.PARTIAL.value,
                ]
            },
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
            "builds_processing_failed": 0,
            "total_pending": 0,
        }

        for r in results:
            status = r["_id"]
            count = r["count"]

            if status in (
                ExtractionStatus.COMPLETED.value,
                ExtractionStatus.PARTIAL.value,
            ):
                stats["builds_processed"] += count
            elif status == ExtractionStatus.FAILED.value:
                stats["builds_processing_failed"] += count
            elif status == ExtractionStatus.PENDING.value:
                stats["total_pending"] += count

        return stats

    def aggregate_prediction_stats(
        self,
        model_repo_config_id: ObjectId,
    ) -> Dict[str, int]:
        """
        Aggregate prediction stats for a repo config.

        Returns a dictionary with:
        - 'predicted': count of builds with predicted_label (successful predictions)
        - 'failed': count of builds with prediction_error (failed predictions)
        - 'pending': count of builds with completed extraction but no prediction yet

        Args:
            model_repo_config_id: The ModelRepoConfig ID

        Returns:
            Dict with prediction stats
        """
        pipeline = [
            {
                "$match": {
                    "model_repo_config_id": model_repo_config_id,
                    "extraction_status": {
                        "$in": [
                            ExtractionStatus.COMPLETED.value,
                            ExtractionStatus.PARTIAL.value,
                        ]
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "predicted": {"$sum": {"$cond": [{"$ne": ["$predicted_label", None]}, 1, 0]}},
                    "failed": {"$sum": {"$cond": [{"$ne": ["$prediction_error", None]}, 1, 0]}},
                    "pending": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$and": [
                                        {"$eq": ["$predicted_label", None]},
                                        {"$eq": ["$prediction_error", None]},
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]
        results = list(self.collection.aggregate(pipeline))

        if results:
            return {
                "predicted": results[0].get("predicted", 0),
                "failed": results[0].get("failed", 0),
                "pending": results[0].get("pending", 0),
            }
        return {"predicted": 0, "failed": 0, "pending": 0}

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

    def aggregate_risk_counts(
        self,
        model_repo_config_id: ObjectId,
    ) -> Dict[str, int]:
        """
        Aggregate builds by predicted risk label.

        Returns a dictionary with counts for each risk level: HIGH, MEDIUM, LOW.
        Only includes builds with successful predictions.

        Args:
            model_repo_config_id: The ModelRepoConfig ID

        Returns:
            Dict with counts per risk level, e.g. {"HIGH": 5, "MEDIUM": 10, "LOW": 20}
        """
        pipeline = [
            {
                "$match": {
                    "model_repo_config_id": model_repo_config_id,
                    "predicted_label": {"$ne": None},
                }
            },
            {"$group": {"_id": "$predicted_label", "count": {"$sum": 1}}},
        ]
        results = list(self.collection.aggregate(pipeline))

        # Convert to dict
        return {r["_id"]: r["count"] for r in results if r["_id"]}

    def find_high_risk_builds(
        self,
        model_repo_config_id: ObjectId,
        limit: int = 10,
    ) -> List[ModelTrainingBuild]:
        """
        Find builds predicted as HIGH risk.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            limit: Maximum number of builds to return

        Returns:
            List of HIGH risk builds, sorted by build_created_at desc
        """
        query = {
            "model_repo_config_id": model_repo_config_id,
            "predicted_label": "HIGH",
        }
        cursor = self.collection.find(query).sort("build_created_at", -1).limit(limit)
        return [ModelTrainingBuild(**doc) for doc in cursor]
