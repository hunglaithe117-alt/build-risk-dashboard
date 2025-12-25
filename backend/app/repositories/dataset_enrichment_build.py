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
    ) -> Iterator[DatasetEnrichmentBuild]:
        """Get all enriched builds for export, sorted by CSV row index. Yields results."""
        query: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }
        if version_id:
            query["dataset_version_id"] = version_id

        cursor = self.collection.find(query).sort("_id", 1).batch_size(100)
        if limit:
            cursor = cursor.limit(limit)
        for doc in cursor:
            yield doc  # Return raw dict for export_utils

    def get_all_feature_keys(
        self,
        dataset_id: ObjectId,
        version_id: Optional[ObjectId] = None,
    ) -> set:
        """Get all unique feature keys for consistent CSV columns.

        Includes keys from both features and scan_metrics fields.
        """
        query: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "extraction_status": ExtractionStatus.COMPLETED.value,
        }
        if version_id:
            query["dataset_version_id"] = version_id

        # Get keys from features field
        pipeline_features = [
            {"$match": query},
            {"$project": {"feature_keys": {"$objectToArray": {"$ifNull": ["$features", {}]}}}},
            {"$unwind": {"path": "$feature_keys", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": None, "keys": {"$addToSet": "$feature_keys.k"}}},
        ]

        # Get keys from scan_metrics field
        pipeline_scan = [
            {"$match": query},
            {"$project": {"scan_keys": {"$objectToArray": {"$ifNull": ["$scan_metrics", {}]}}}},
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
        Calculate statistics for features
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

        # 2. Calculate min, max, avg, and count
        group_fields = {"_id": None}
        for feature in features:
            field_path = f"$features.{feature}"

            # Numeric stat
            group_fields[f"{feature}__min"] = {"$min": field_path}
            group_fields[f"{feature}__max"] = {"$max": field_path}
            group_fields[f"{feature}__avg"] = {"$avg": field_path}

            # Count non-null values
            # $cond with $ne: [val, None] correctly counts 1 for any value (including False/0) except null/missing
            group_fields[f"{feature}__non_null"] = {
                "$sum": {"$cond": [{"$ne": [field_path, None]}, 1, 0]}
            }

        pipeline = [{"$match": query}, {"$group": group_fields}]

        try:
            agg_results = list(self.collection.aggregate(pipeline, allowDiskUse=True))
        except Exception:
            return {}

        result_doc = agg_results[0] if agg_results else {}

        # 3. Type Inference (via sampling)
        sample_docs = list(self.collection.find(query, {"features": 1}).limit(5))

        stats = {}
        for feature in features:
            # Determine type from samples
            value_type = "unknown"
            for doc in sample_docs:
                val = doc.get("features", {}).get(feature)
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
        Backfill scan metrics to ALL builds in a version matching commit_sha.

        This is called when a scan completes to update all enrichment builds
        in the same version that were triggered by the same commit.

        Args:
            version_id: DatasetVersion ID
            commit_sha: Git commit SHA
            scan_features: Filtered metrics to add
            prefix: Feature prefix ('sonar_' or 'trivy_')

        Returns:
            Number of documents updated.
        """
        # Find all enrichment builds in this version with matching commit
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
            {"$project": {"_id": 1}},
        ]

        matching_ids = [doc["_id"] for doc in self.collection.aggregate(pipeline)]

        if not matching_ids:
            return 0

        # Write to scan_metrics field with prefix
        set_ops = {f"scan_metrics.{prefix}{k}": v for k, v in scan_features.items()}
        set_ops["updated_at"] = datetime.utcnow()

        result = self.collection.update_many(
            {"_id": {"$in": matching_ids}},
            {"$set": set_ops},
        )

        return result.modified_count

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

        Counts builds by presence of sonar_*/trivy_* in scan_metrics field.
        """
        pipeline = [
            {"$match": {"dataset_version_id": version_id}},
            {
                "$project": {
                    "has_sonar": {
                        "$gt": [
                            {
                                "$size": {
                                    "$filter": {
                                        "input": {
                                            "$objectToArray": {"$ifNull": ["$scan_metrics", {}]}
                                        },
                                        "cond": {
                                            "$regexMatch": {"input": "$$this.k", "regex": "^sonar_"}
                                        },
                                    }
                                }
                            },
                            0,
                        ]
                    },
                    "has_trivy": {
                        "$gt": [
                            {
                                "$size": {
                                    "$filter": {
                                        "input": {
                                            "$objectToArray": {"$ifNull": ["$scan_metrics", {}]}
                                        },
                                        "cond": {
                                            "$regexMatch": {"input": "$$this.k", "regex": "^trivy_"}
                                        },
                                    }
                                }
                            },
                            0,
                        ]
                    },
                    "extraction_status": 1,
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "with_sonar": {"$sum": {"$cond": ["$has_sonar", 1, 0]}},
                    "with_trivy": {"$sum": {"$cond": ["$has_trivy", 1, 0]}},
                    "completed": {
                        "$sum": {"$cond": [{"$eq": ["$extraction_status", "completed"]}, 1, 0]}
                    },
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))
        if not results:
            return {"total": 0, "with_sonar": 0, "with_trivy": 0, "completed": 0}

        data = results[0]
        return {
            "total": data.get("total", 0),
            "with_sonar": data.get("with_sonar", 0),
            "with_trivy": data.get("with_trivy", 0),
            "completed": data.get("completed", 0),
            "scan_complete": data.get("with_sonar", 0) > 0 or data.get("with_trivy", 0) > 0,
        }

    def list_by_version_with_details(
        self,
        dataset_version_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        List builds for a version with repo name and web url.
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
                            "$addFields": {
                                "repo_full_name": {"$arrayElemAt": ["$repo.full_name", 0]},
                                "repo_url": {"$arrayElemAt": ["$repo.url", 0]},
                                "provider": {"$arrayElemAt": ["$repo.provider", 0]},
                                "web_url": {"$arrayElemAt": ["$run.web_url", 0]},
                            }
                        },
                        {"$project": {"repo": 0, "run": 0}},
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
