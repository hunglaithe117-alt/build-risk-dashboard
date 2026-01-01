"""Repository for DatasetEnrichmentBuild entities (builds for dataset enrichment)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from bson import ObjectId
from pymongo.client_session import ClientSession

from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.entities.enums import ExtractionStatus
from app.repositories.base import BaseRepository


class DatasetEnrichmentBuildRepository(BaseRepository[DatasetEnrichmentBuild]):
    """Repository for DatasetEnrichmentBuild entities (Dataset enrichment flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "dataset_enrichment_builds", DatasetEnrichmentBuild)

    def find_by_dataset_build_id(
        self,
        dataset_id: ObjectId,
        dataset_build_id: ObjectId,
    ) -> Optional[DatasetEnrichmentBuild]:
        """Find build by dataset and dataset build ID."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "dataset_build_id": dataset_build_id,
            }
        )
        return DatasetEnrichmentBuild(**doc) if doc else None

    def find_by_workflow_run(
        self,
        dataset_id: ObjectId,
        raw_build_run_id: ObjectId,
    ) -> Optional[DatasetEnrichmentBuild]:
        """Find build by dataset and workflow run."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "raw_build_run_id": raw_build_run_id,
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
            query["extraction_status"] = status.value if hasattr(status, "value") else status

        return self.paginate(query, sort=[("_id", 1)], skip=skip, limit=limit)

    def list_by_version(
        self,
        dataset_version_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[DatasetEnrichmentBuild], int]:
        """List builds for a dataset version with pagination."""
        query = {"dataset_version_id": dataset_version_id}
        return self.paginate(query, sort=[("_id", 1)], skip=skip, limit=limit)

    def find_by_version(
        self,
        dataset_version_id: str | ObjectId,
    ) -> List[DatasetEnrichmentBuild]:
        """
        Find all builds for a dataset version.

        Used for statistics calculation where we need the full dataset.
        """
        oid = self._to_object_id(dataset_version_id)
        if not oid:
            return []

        return self.find_many({"dataset_version_id": oid})

    def find_by_version_with_features(
        self,
        dataset_version_id: str | ObjectId,
    ) -> List[Dict[str, Any]]:
        """
        Find all builds for a version with features from FeatureVector.

        Returns dicts with merged build info + features (for statistics).
        """
        oid = self._to_object_id(dataset_version_id)
        if not oid:
            return []

        pipeline = [
            {"$match": {"dataset_version_id": oid}},
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "fv",
                }
            },
            {"$unwind": {"path": "$fv", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "_id": 1,
                    "extraction_status": 1,
                    "extraction_error": 1,
                    "enriched_at": 1,
                    "feature_vector_id": 1,
                    # Features from FeatureVector
                    "features": {"$ifNull": ["$fv.features", {}]},
                    "feature_count": {"$ifNull": ["$fv.feature_count", 0]},
                    "skipped_features": {"$ifNull": ["$fv.skipped_features", []]},
                    "missing_resources": {"$ifNull": ["$fv.missing_resources", []]},
                }
            },
        ]

        return list(self.collection.aggregate(pipeline))

    def find_by_import_build(
        self,
        import_build_id: str | ObjectId,
    ) -> Optional[DatasetEnrichmentBuild]:
        """Find enrichment build by its import build ID."""
        oid = self._to_object_id(import_build_id)
        if not oid:
            return None
        doc = self.collection.find_one({"dataset_import_build_id": oid})
        return DatasetEnrichmentBuild(**doc) if doc else None

    def upsert_for_import_build(
        self,
        dataset_version_id: str,
        dataset_id: str,
        dataset_build_id: str,
        dataset_import_build_id: str,
        raw_repo_id: str,
        raw_build_run_id: str,
    ) -> DatasetEnrichmentBuild:
        """
        Create or get DatasetEnrichmentBuild for an import build.

        Returns existing if already created, creates new if not.
        """
        import_oid = ObjectId(dataset_import_build_id)

        # Try to find existing
        existing = self.collection.find_one({"dataset_import_build_id": import_oid})
        if existing:
            return DatasetEnrichmentBuild(**existing)

        # Create new
        now = datetime.utcnow()
        doc = {
            "dataset_version_id": ObjectId(dataset_version_id),
            "dataset_id": ObjectId(dataset_id),
            "dataset_build_id": ObjectId(dataset_build_id),
            "dataset_import_build_id": import_oid,
            "raw_repo_id": ObjectId(raw_repo_id),
            "raw_build_run_id": ObjectId(raw_build_run_id),
            "extraction_status": ExtractionStatus.PENDING.value,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(doc)
        doc["_id"] = result.inserted_id
        return DatasetEnrichmentBuild(**doc)

    def aggregate_stats_by_version(
        self,
        version_id: str | ObjectId,
    ) -> Dict[str, int]:
        """
        Get extraction stats for a version.

        Returns: {completed: N, partial: N, failed: N, pending: N}
        """
        oid = self._to_object_id(version_id)
        if not oid:
            return {"completed": 0, "partial": 0, "failed": 0, "pending": 0}

        pipeline = [
            {"$match": {"dataset_version_id": oid}},
            {
                "$group": {
                    "_id": "$extraction_status",
                    "count": {"$sum": 1},
                }
            },
        ]

        stats = {"completed": 0, "partial": 0, "failed": 0, "pending": 0}
        for doc in self.collection.aggregate(pipeline):
            status = doc["_id"]
            if status in stats:
                stats[status] = doc["count"]

        return stats

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
            query["extraction_status"] = status.value if hasattr(status, "value") else status
        return self.collection.count_documents(query)

    def get_enriched_for_export(
        self,
        dataset_id: ObjectId,
        version_id: Optional[ObjectId] = None,
        limit: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Get all enriched builds for export with features from FeatureVector.

        Joins with feature_vectors collection to get features and scan_metrics.
        Yields raw dicts for export_utils.
        """
        match_query: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }
        if version_id:
            match_query["dataset_version_id"] = version_id

        pipeline = [
            {"$match": match_query},
            {"$sort": {"_id": 1}},
            # Join with feature_vectors to get features and scan_metrics
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "feature_vector",
                }
            },
            # Unwind the joined array (1:1 relationship)
            {"$unwind": {"path": "$feature_vector", "preserveNullAndEmptyArrays": True}},
            # Project only features and scan_metrics for export
            {
                "$project": {
                    "_id": 1,
                    "dataset_id": 1,
                    "dataset_version_id": 1,
                    "raw_repo_id": 1,
                    "raw_build_run_id": 1,
                    "dataset_build_id": 1,
                    # Only features and scan_metrics from FeatureVector
                    "features": {"$ifNull": ["$feature_vector.features", {}]},
                    "scan_metrics": {"$ifNull": ["$feature_vector.scan_metrics", {}]},
                }
            },
        ]

        if limit:
            pipeline.append({"$limit": limit})

        cursor = self.collection.aggregate(pipeline, batchSize=100)
        for doc in cursor:
            yield doc

    def get_all_feature_keys(
        self,
        dataset_id: ObjectId,
        version_id: Optional[ObjectId] = None,
    ) -> set:
        """
        Get all unique feature keys for consistent CSV columns.

        Joins with feature_vectors to get keys from features and scan_metrics fields.
        """
        match_query: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }
        if version_id:
            match_query["dataset_version_id"] = version_id

        # Pipeline to get feature keys from joined feature_vectors
        pipeline_features = [
            {"$match": match_query},
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "fv",
                }
            },
            {"$unwind": {"path": "$fv", "preserveNullAndEmptyArrays": False}},
            {"$project": {"feature_keys": {"$objectToArray": {"$ifNull": ["$fv.features", {}]}}}},
            {"$unwind": {"path": "$feature_keys", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": None, "keys": {"$addToSet": "$feature_keys.k"}}},
        ]

        # Pipeline to get scan_metrics keys from joined feature_vectors
        pipeline_scan = [
            {"$match": match_query},
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "fv",
                }
            },
            {"$unwind": {"path": "$fv", "preserveNullAndEmptyArrays": False}},
            {"$project": {"scan_keys": {"$objectToArray": {"$ifNull": ["$fv.scan_metrics", {}]}}}},
            {"$unwind": {"path": "$scan_keys", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": None, "keys": {"$addToSet": "$scan_keys.k"}}},
        ]

        all_keys = set()

        feature_result = list(self.collection.aggregate(pipeline_features))
        if feature_result:
            all_keys.update(feature_result[0].get("keys", []))

        scan_result = list(self.collection.aggregate(pipeline_scan))
        if scan_result:
            all_keys.update(scan_result[0].get("keys", []))

        return all_keys

    def delete_by_dataset(
        self, dataset_id: ObjectId, session: Optional["ClientSession"] = None
    ) -> int:
        """Delete all builds for a dataset.

        Args:
            dataset_id: Dataset ID to delete builds for
            session: Optional MongoDB session for transaction support
        """
        result = self.collection.delete_many({"dataset_id": dataset_id}, session=session)
        return result.deleted_count

    def delete_by_version(self, version_id: str, session: Optional["ClientSession"] = None) -> int:
        """Delete all builds for a version.

        Args:
            version_id: Version ID to delete builds for
            session: Optional MongoDB session for transaction support
        """
        result = self.collection.delete_many(
            {"dataset_version_id": ObjectId(version_id)}, session=session
        )
        return result.deleted_count

    def get_feature_stats(
        self,
        dataset_id: ObjectId,
        version_id: ObjectId,
        features: List[str],
    ) -> Dict[str, Any]:
        """
        Calculate statistics for features from FeatureVector.

        Joins with feature_vectors collection to get features.
        """
        if not features:
            return {}

        query = {
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
        }

        # 1. Get total count
        total_docs = self.collection.count_documents(query)
        if total_docs == 0:
            return {}

        # 2. Calculate min, max, avg, and count using aggregation with $lookup
        group_fields: Dict[str, Any] = {"_id": None}
        for feature in features:
            field_path = f"$fv.features.{feature}"

            # Numeric stat
            group_fields[f"{feature}__min"] = {"$min": field_path}
            group_fields[f"{feature}__max"] = {"$max": field_path}
            group_fields[f"{feature}__avg"] = {"$avg": field_path}

            # Count non-null values
            group_fields[f"{feature}__non_null"] = {
                "$sum": {"$cond": [{"$ne": [field_path, None]}, 1, 0]}
            }

        pipeline = [
            {"$match": query},
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "fv",
                }
            },
            {"$unwind": {"path": "$fv", "preserveNullAndEmptyArrays": True}},
            {"$group": group_fields},
        ]

        try:
            agg_results = list(self.collection.aggregate(pipeline, allowDiskUse=True))
        except Exception:
            return {}

        result_doc = agg_results[0] if agg_results else {}

        # 3. Type Inference (via sampling) - also needs to join with feature_vectors
        sample_pipeline = [
            {"$match": query},
            {"$limit": 5},
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "feature_vector_id",
                    "foreignField": "_id",
                    "as": "fv",
                }
            },
            {"$unwind": {"path": "$fv", "preserveNullAndEmptyArrays": True}},
            {"$project": {"features": "$fv.features"}},
        ]
        sample_docs = list(self.collection.aggregate(sample_pipeline))

        stats = {}
        for feature in features:
            # Determine type from samples
            value_type = "unknown"
            for doc in sample_docs:
                val = doc.get("features", {}).get(feature) if doc.get("features") else None
                if val is not None:
                    if isinstance(val, bool):
                        value_type = "boolean"
                    elif isinstance(val, (int, float)):
                        value_type = "numeric"
                    elif isinstance(val, str):
                        value_type = "string"
                    elif isinstance(val, list):
                        value_type = "array"
                    break  # Found a type

            # Retrieve stats from aggregation result
            non_null = result_doc.get(f"{feature}__non_null", 0)
            missing = total_docs - non_null
            missing_rate = (missing / total_docs * 100) if total_docs else 0

            feat_stat = {
                "non_null": non_null,
                "missing": missing,
                "missing_rate": round(missing_rate, 1),
                "type": value_type,
            }

            # Add numeric stats if applicable
            # Note: $avg returns null if no numeric values existed
            avg_val = result_doc.get(f"{feature}__avg")
            if avg_val is not None:
                feat_stat["min"] = result_doc.get(f"{feature}__min")
                feat_stat["max"] = result_doc.get(f"{feature}__max")
                feat_stat["avg"] = round(avg_val, 2)
                if value_type == "unknown":
                    value_type = "numeric"

            feat_stat["type"] = value_type
            stats[feature] = feat_stat

        return stats

    def backfill_scan_features(
        self,
        build_id: ObjectId,
        scan_features: Dict[str, Any],
        prefix: str = "sonar_",
    ) -> None:
        """
        Add scan metrics to the scan_metrics field.

        Args:
            build_id: DatasetEnrichmentBuild ID
            scan_features: Raw metrics from scan tool
            prefix: Feature prefix ('sonar_' or 'trivy_')
        """
        # Write to scan_metrics field with prefix
        set_ops = {f"scan_metrics.{prefix}{k}": v for k, v in scan_features.items()}
        set_ops["updated_at"] = datetime.utcnow()

        self.collection.update_one({"_id": build_id}, {"$set": set_ops})

    def backfill_by_commit_in_version(
        self,
        version_id: ObjectId,
        commit_sha: str,
        scan_features: Dict[str, Any],
        prefix: str = "sonar_",
    ) -> int:
        """
        Backfill scan metrics to FeatureVector for ALL builds in a version matching commit_sha.

        This is called when a scan completes to update FeatureVector.scan_metrics
        for all enrichment builds in the same version that were triggered by the same commit.

        Args:
            version_id: DatasetVersion ID
            commit_sha: Git commit SHA
            scan_features: Filtered metrics to add
            prefix: Feature prefix ('sonar_' or 'trivy_')

        Returns:
            Number of FeatureVector documents updated.
        """
        # Find all enrichment builds in this version with matching commit
        # and get their feature_vector_id
        pipeline = [
            {"$match": {"dataset_version_id": version_id}},
            {
                "$lookup": {
                    "from": "raw_build_runs",
                    "localField": "raw_build_run_id",
                    "foreignField": "_id",
                    "as": "build_run",
                }
            },
            {"$unwind": "$build_run"},
            {"$match": {"build_run.commit_sha": commit_sha}},
            {"$match": {"feature_vector_id": {"$ne": None}}},
            {"$project": {"feature_vector_id": 1}},
        ]

        matching_docs = list(self.collection.aggregate(pipeline))
        feature_vector_ids = [
            doc["feature_vector_id"] for doc in matching_docs if doc.get("feature_vector_id")
        ]

        if not feature_vector_ids:
            return 0

        # Write to FeatureVector.scan_metrics with prefix
        set_ops = {f"scan_metrics.{prefix}{k}": v for k, v in scan_features.items()}
        set_ops["updated_at"] = datetime.utcnow()

        feature_vectors_collection = self.db["feature_vectors"]
        result = feature_vectors_collection.update_many(
            {"_id": {"$in": feature_vector_ids}},
            {"$set": set_ops},
        )

        return result.modified_count

    def mark_in_progress_as_failed(
        self,
        version_id: str,
        error_message: str,
    ) -> int:
        """
        Mark all IN_PROGRESS enrichment builds as FAILED.

        Used when processing chain fails to mark incomplete builds.
        """
        result = self.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "extraction_status": ExtractionStatus.IN_PROGRESS.value,
            },
            {
                "$set": {
                    "extraction_status": ExtractionStatus.FAILED.value,
                    "extraction_error": error_message,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count

    def count_by_status(
        self,
        version_id: ObjectId,
        status: str,
    ) -> int:
        """Count enrichment builds by status for a version."""
        return self.collection.count_documents(
            {
                "dataset_version_id": version_id,
                "extraction_status": status,
            }
        )

    def _update_feature_count(self, build_id: ObjectId) -> None:
        """Recalculate feature_count based on features dict size."""
        doc = self.collection.find_one({"_id": build_id}, {"features": 1})
        if doc:
            feature_count = len(doc.get("features", {}))
            self.collection.update_one(
                {"_id": build_id},
                {"$set": {"feature_count": feature_count}},
            )

    def get_scan_status_by_version(
        self,
        version_id: ObjectId,
    ) -> Dict[str, Any]:
        """
        Get scan metrics status for a version.

        Uses CommitScan collections for simpler queries instead of
        scanning embedded scan_metrics fields.
        """
        from app.entities.sonar_commit_scan import SonarScanStatus
        from app.entities.trivy_commit_scan import TrivyScanStatus
        from app.repositories.sonar_commit_scan import SonarCommitScanRepository
        from app.repositories.trivy_commit_scan import TrivyCommitScanRepository

        sonar_repo = SonarCommitScanRepository(self.db)
        trivy_repo = TrivyCommitScanRepository(self.db)

        # Count scans by status - simple indexed queries
        sonar_total = sonar_repo.count_by_version(version_id)
        sonar_completed = sonar_repo.count_by_version_and_status(
            version_id, SonarScanStatus.COMPLETED
        )
        sonar_failed = sonar_repo.count_by_version_and_status(version_id, SonarScanStatus.FAILED)

        trivy_total = trivy_repo.count_by_version(version_id)
        trivy_completed = trivy_repo.count_by_version_and_status(
            version_id, TrivyScanStatus.COMPLETED
        )
        trivy_failed = trivy_repo.count_by_version_and_status(version_id, TrivyScanStatus.FAILED)

        # Get enrichment build count
        total_builds = self.collection.count_documents({"dataset_version_id": version_id})
        completed_builds = self.collection.count_documents(
            {
                "dataset_version_id": version_id,
                "extraction_status": "completed",
            }
        )

        return {
            "total": total_builds,
            "completed": completed_builds,
            "sonar": {
                "total": sonar_total,
                "completed": sonar_completed,
                "failed": sonar_failed,
                "pending": sonar_total - sonar_completed - sonar_failed,
            },
            "trivy": {
                "total": trivy_total,
                "completed": trivy_completed,
                "failed": trivy_failed,
                "pending": trivy_total - trivy_completed - trivy_failed,
            },
            "with_sonar": sonar_completed,
            "with_trivy": trivy_completed,
            "scan_complete": (
                (sonar_total == 0 or sonar_completed == sonar_total)
                and (trivy_total == 0 or trivy_completed == trivy_total)
            ),
        }

    def list_by_version_with_details(
        self,
        dataset_version_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        List builds for a version with repo name, web url, and features from FeatureVector.
        """
        pipeline = [
            {"$match": {"dataset_version_id": dataset_version_id}},
            {"$sort": {"_id": 1}},
            {
                "$facet": {
                    "metadata": [{"$count": "total"}],
                    "data": [
                        {"$skip": skip},
                        {"$limit": limit},
                        {
                            "$lookup": {
                                "from": "raw_repositories",
                                "localField": "raw_repo_id",
                                "foreignField": "_id",
                                "as": "repo",
                            }
                        },
                        {
                            "$lookup": {
                                "from": "raw_build_runs",
                                "localField": "raw_build_run_id",
                                "foreignField": "_id",
                                "as": "run",
                            }
                        },
                        {
                            "$lookup": {
                                "from": "dataset_repo_stats",
                                "let": {"dataset_id": "$dataset_id", "repo_id": "$raw_repo_id"},
                                "pipeline": [
                                    {
                                        "$match": {
                                            "$expr": {
                                                "$and": [
                                                    {"$eq": ["$dataset_id", "$$dataset_id"]},
                                                    {"$eq": ["$raw_repo_id", "$$repo_id"]},
                                                ]
                                            }
                                        }
                                    }
                                ],
                                "as": "repo_stats",
                            }
                        },
                        # Join with feature_vectors to get features and scan_metrics
                        {
                            "$lookup": {
                                "from": "feature_vectors",
                                "localField": "feature_vector_id",
                                "foreignField": "_id",
                                "as": "feature_vector",
                            }
                        },
                        {
                            "$addFields": {
                                "repo_full_name": {"$arrayElemAt": ["$repo.full_name", 0]},
                                "provider": {"$arrayElemAt": ["$repo_stats.ci_provider", 0]},
                                "web_url": {"$arrayElemAt": ["$run.web_url", 0]},
                                # Features from FeatureVector
                                "features": {
                                    "$ifNull": [
                                        {"$arrayElemAt": ["$feature_vector.features", 0]},
                                        {},
                                    ]
                                },
                                "scan_metrics": {
                                    "$ifNull": [
                                        {"$arrayElemAt": ["$feature_vector.scan_metrics", 0]},
                                        {},
                                    ]
                                },
                                "feature_count": {
                                    "$ifNull": [
                                        {"$arrayElemAt": ["$feature_vector.feature_count", 0]},
                                        0,
                                    ]
                                },
                                "is_missing_commit": {
                                    "$ifNull": [
                                        {"$arrayElemAt": ["$feature_vector.is_missing_commit", 0]},
                                        False,
                                    ]
                                },
                                "missing_resources": {
                                    "$ifNull": [
                                        {"$arrayElemAt": ["$feature_vector.missing_resources", 0]},
                                        [],
                                    ]
                                },
                                "skipped_features": {
                                    "$ifNull": [
                                        {"$arrayElemAt": ["$feature_vector.skipped_features", 0]},
                                        [],
                                    ]
                                },
                            }
                        },
                        {"$project": {"repo": 0, "run": 0, "repo_stats": 0, "feature_vector": 0}},
                    ],
                }
            },
        ]

        result = list(self.collection.aggregate(pipeline))
        if not result:
            return [], 0

        data = result[0]["data"]
        metadata = result[0]["metadata"]
        total = metadata[0]["total"] if metadata else 0

        return data, total
