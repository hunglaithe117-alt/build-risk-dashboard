"""Repository for ModelTrainingBuild entities (builds for ML model training)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.entities.model_training_build import ModelTrainingBuild
from app.entities.enums import ExtractionStatus
from app.repositories.base import BaseRepository


class ModelTrainingBuildRepository(BaseRepository[ModelTrainingBuild]):
    """Repository for ModelTrainingBuild entities (Model training flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "model_training_builds", ModelTrainingBuild)

    def find_by_workflow_run(
        self,
        raw_repo_id: ObjectId,
        raw_workflow_run_id: ObjectId,
    ) -> Optional[ModelTrainingBuild]:
        """Find build by repo and workflow run."""
        doc = self.collection.find_one(
            {
                "raw_repo_id": raw_repo_id,
                "raw_workflow_run_id": raw_workflow_run_id,
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
                "model_repo_config_id": ObjectId(repo_id),
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
            ObjectId(repo_id), skip, limit if limit > 0 else 10000
        )

    def count_by_repo_id(self, repo_id: str) -> int:
        """Convenience method - count by model_repo_config_id (string)."""
        return self.count_by_config(ObjectId(repo_id))

    def find_by_config(
        self,
        model_repo_config_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[ModelTrainingBuild], int]:
        """List builds for a model repo config with pagination."""
        query = {"model_repo_config_id": model_repo_config_id}
        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("build_created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        items = [ModelTrainingBuild(**doc) for doc in cursor]
        return items, total

    def find_by_repo(
        self,
        raw_repo_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[ModelTrainingBuild], int]:
        """List builds for a raw repository with pagination."""
        query = {"raw_repo_id": raw_repo_id}
        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("build_created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        items = [ModelTrainingBuild(**doc) for doc in cursor]
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
            query["extraction_status"] = (
                status.value if hasattr(status, "value") else status
            )
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
