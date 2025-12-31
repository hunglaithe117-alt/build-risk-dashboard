"""Repository for FeatureVector entities - single source of truth for extracted features."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo import ASCENDING, IndexModel, ReturnDocument
from pymongo.collection import Collection

from app.entities.enums import ExtractionStatus
from app.entities.feature_vector import FeatureVector
from app.repositories.base import BaseRepository


class FeatureVectorRepository(BaseRepository[FeatureVector]):
    """Repository for FeatureVector entities (shared feature storage)."""

    def __init__(self, db) -> None:
        super().__init__(db, "feature_vectors", FeatureVector)
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes for efficient lookups."""
        indexes = [
            # Unique constraint on (raw_repo_id, raw_build_run_id)
            IndexModel(
                [("raw_repo_id", ASCENDING), ("raw_build_run_id", ASCENDING)],
                unique=True,
                name="unique_repo_build",
            ),
            # Temporal chain lookup (for prev_build_history_features)
            IndexModel(
                [("raw_repo_id", ASCENDING), ("tr_prev_build", ASCENDING)],
                name="temporal_chain_lookup",
            ),
            # Lookup by raw_build_run_id alone
            IndexModel(
                [("raw_build_run_id", ASCENDING)],
                name="build_run_lookup",
            ),
        ]
        try:
            self.collection.create_indexes(indexes)
        except Exception:
            # Indexes may already exist with different options
            pass

    def find_by_build_run(
        self,
        raw_build_run_id: ObjectId,
    ) -> Optional[FeatureVector]:
        """Find feature vector by raw build run ID."""
        doc = self.collection.find_one({"raw_build_run_id": raw_build_run_id})
        return FeatureVector(**doc) if doc else None

    def find_by_repo_and_build(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_id: ObjectId,
    ) -> Optional[FeatureVector]:
        """Find feature vector by repo and build run (the unique key)."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": raw_build_run_id,
            }
        )
        return FeatureVector(**doc) if doc else None

    def upsert_features(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_id: ObjectId,
        features: Dict[str, Any],
        extraction_status: ExtractionStatus = ExtractionStatus.COMPLETED,
        extraction_error: Optional[str] = None,
        dag_version: str = "1.0",
        tr_prev_build: Optional[str] = None,
        is_missing_commit: bool = False,
        missing_resources: Optional[List[str]] = None,
        skipped_features: Optional[List[str]] = None,
    ) -> FeatureVector:
        """
        Atomic upsert feature vector by business key (raw_repo_id + raw_build_run_id).

        Creates new document or updates existing one atomically.
        """
        status_value = (
            extraction_status.value if hasattr(extraction_status, "value") else extraction_status
        )

        update_doc = {
            "features": features,
            "feature_count": len(features) if features else 0,
            "extraction_status": status_value,
            "extraction_error": extraction_error,
            "dag_version": dag_version,
            "tr_prev_build": tr_prev_build,
            "is_missing_commit": is_missing_commit,
            "missing_resources": missing_resources or [],
            "skipped_features": skipped_features or [],
            "computed_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        doc = self.collection.find_one_and_update(
            {
                "raw_repo_id": raw_repo_id,
                "raw_build_run_id": raw_build_run_id,
            },
            {
                "$set": update_doc,
                "$setOnInsert": {
                    "raw_repo_id": raw_repo_id,
                    "raw_build_run_id": raw_build_run_id,
                    "created_at": datetime.utcnow(),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return FeatureVector(**doc)

    def get_or_create(
        self,
        raw_repo_id: ObjectId,
        raw_build_run_id: ObjectId,
    ) -> Tuple[FeatureVector, bool]:
        """
        Get existing feature vector or create new pending one.

        Returns (feature_vector, was_created).
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
                    "extraction_status": ExtractionStatus.PENDING.value,
                    "features": {},
                    "feature_count": 0,
                    "dag_version": "1.0",
                    "created_at": datetime.utcnow(),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        feature_vector = FeatureVector(**doc)
        was_created = (
            doc.get("created_at") is not None
            and (datetime.utcnow() - doc.get("created_at", datetime.utcnow())).total_seconds() < 2
        )
        return feature_vector, was_created

    def find_by_tr_prev_build(
        self,
        raw_repo_id: ObjectId,
        tr_prev_build: str,
    ) -> Optional[FeatureVector]:
        """
        Find the next build in the temporal chain.

        Used by temporal features to walk backward through build history.
        """
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "tr_prev_build": tr_prev_build,
            }
        )
        return FeatureVector(**doc) if doc else None

    def find_by_ci_run_id(
        self,
        raw_repo_id: ObjectId,
        ci_run_id: str,
    ) -> Optional[FeatureVector]:
        """
        Find feature vector by CI run ID (stored in tr_prev_build of next build).

        Looks up by querying features.tr_prev_build field.
        """
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "features.tr_prev_build": ci_run_id,
            }
        )
        return FeatureVector(**doc) if doc else None

    def find_many_by_raw_build_run_ids(
        self,
        raw_build_run_ids: List[ObjectId],
    ) -> Dict[str, FeatureVector]:
        """
        Batch query: Find feature vectors by raw_build_run_ids.

        Returns dict mapping raw_build_run_id (str) -> FeatureVector for O(1) lookup.
        """
        if not raw_build_run_ids:
            return {}

        cursor = self.collection.find({"raw_build_run_id": {"$in": raw_build_run_ids}})
        return {str(doc["raw_build_run_id"]): FeatureVector(**doc) for doc in cursor}

    def walk_temporal_chain(
        self,
        raw_repo_id: ObjectId,
        starting_ci_run_id: str,
        max_depth: int = 20,
    ) -> List[FeatureVector]:
        """
        Walk backward through the temporal chain of builds.

        Starts from starting_ci_run_id and follows tr_prev_build links.
        Used by prev_build_history_features.

        Args:
            raw_repo_id: Repository ID
            starting_ci_run_id: CI run ID to start from (the "previous" build)
            max_depth: Maximum number of builds to retrieve

        Returns:
            List of FeatureVector in temporal order (newest first)
        """

        result: List[FeatureVector] = []
        current_ci_run_id = starting_ci_run_id

        # Need to lookup raw_build_run by ci_run_id to get ObjectId
        db = self.collection.database
        raw_build_run_collection = db["raw_build_runs"]

        while current_ci_run_id and len(result) < max_depth:
            # Find the raw_build_run by ci_run_id
            raw_build_doc = raw_build_run_collection.find_one(
                {
                    "raw_repo_id": raw_repo_id,
                    "ci_run_id": current_ci_run_id,
                }
            )

            if not raw_build_doc:
                break

            # Find the feature vector for this build
            feature_doc = self.collection.find_one(
                {
                    "raw_repo_id": raw_repo_id,
                    "raw_build_run_id": raw_build_doc["_id"],
                }
            )

            if not feature_doc:
                break

            feature_vector = FeatureVector(**feature_doc)
            result.append(feature_vector)

            # Get the tr_prev_build from features to continue the chain
            current_ci_run_id = feature_vector.features.get("tr_prev_build")

        return result

    def update_normalized_features(
        self,
        feature_vector_id: ObjectId,
        normalized_features: Dict[str, float],
    ) -> Optional[FeatureVector]:
        """
        Update normalized features for a feature vector.

        Called during prediction phase to store model-ready features.

        Args:
            feature_vector_id: The FeatureVector ObjectId
            normalized_features: Dict of normalized feature values (TEMPORAL + STATIC)

        Returns:
            Updated FeatureVector or None if not found
        """
        doc = self.collection.find_one_and_update(
            {"_id": feature_vector_id},
            {
                "$set": {
                    "normalized_features": normalized_features,
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return FeatureVector(**doc) if doc else None

    def delete_by_raw_repo(
        self,
        raw_repo_id: ObjectId,
        session=None,
    ) -> int:
        """Delete all feature vectors for a repository."""
        result = self.collection.delete_many(
            {"raw_repo_id": raw_repo_id},
            session=session,
        )
        return result.deleted_count

    def get_collection(self) -> Collection:
        """Get the underlying MongoDB collection (for Hamilton DAG inputs)."""
        return self.collection
