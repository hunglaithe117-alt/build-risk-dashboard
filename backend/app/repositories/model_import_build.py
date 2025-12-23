"""
ModelImportBuild Repository - Database operations for model import builds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from bson import ObjectId
from pymongo.synchronous.client_session import ClientSession

from app.entities.model_import_build import ModelImportBuild, ModelImportBuildStatus
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    pass


class ModelImportBuildRepository(BaseRepository[ModelImportBuild]):
    """Repository for ModelImportBuild operations."""

    def __init__(self, db):
        super().__init__(db, ModelImportBuild)

    def find_by_repo_config(
        self,
        config_id: str,
        status: Optional[ModelImportBuildStatus] = None,
        import_version: Optional[int] = None,
    ) -> List[ModelImportBuild]:
        """
        Find all builds for a repo config, optionally filtered by status.

        Args:
            config_id: ModelRepoConfig ID
            status: Optional status filter
            import_version: Optional import version filter

        Returns:
            List of ModelImportBuild entities
        """
        query = {"model_repo_config_id": ObjectId(config_id)}
        if status:
            query["status"] = status.value if hasattr(status, "value") else status
        if import_version:
            query["import_version"] = import_version
        return self.find_many(query)

    def find_fetched_builds(
        self, config_id: str, import_version: Optional[int] = None
    ) -> List[ModelImportBuild]:
        """Find successfully fetched builds."""
        return self.find_by_repo_config(
            config_id, status=ModelImportBuildStatus.FETCHED, import_version=import_version
        )

    def count_by_status(self, config_id: str) -> dict:
        """
        Get count of builds by status for a repo config.

        Returns:
            Dict mapping status -> count
        """
        pipeline = [
            {"$match": {"model_repo_config_id": ObjectId(config_id)}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        results = list(self.collection.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}

    def bulk_insert(self, builds: List[ModelImportBuild]) -> List[ModelImportBuild]:
        """
        Insert multiple builds in one operation.

        Args:
            builds: List of ModelImportBuild entities

        Returns:
            List of inserted entities with IDs
        """
        if not builds:
            return []

        docs = [b.model_dump(by_alias=True, exclude={"id"}) for b in builds]
        result = self.collection.insert_many(docs)

        for build, inserted_id in zip(builds, result.inserted_ids, strict=False):
            build.id = inserted_id
        return builds

    def find_by_business_key(
        self,
        config_id: str,
        raw_build_run_id: str,
    ) -> Optional[ModelImportBuild]:
        """Find by unique business key (config + raw_build_run)."""
        return self.find_one(
            {
                "model_repo_config_id": ObjectId(config_id),
                "raw_build_run_id": ObjectId(raw_build_run_id),
            }
        )

    def get_commit_shas(self, config_id: str, import_version: Optional[int] = None) -> List[str]:
        """Get unique commit SHAs for ingestion."""
        query = {
            "model_repo_config_id": ObjectId(config_id),
            "status": ModelImportBuildStatus.FETCHED.value,
        }
        if import_version:
            query["import_version"] = import_version

        result = self.collection.distinct("commit_sha", query)
        return [sha for sha in result if sha]

    def get_ci_run_ids(self, config_id: str, import_version: Optional[int] = None) -> List[str]:
        """Get CI run IDs for log download."""
        query = {
            "model_repo_config_id": ObjectId(config_id),
            "status": ModelImportBuildStatus.FETCHED.value,
        }
        if import_version:
            query["import_version"] = import_version

        result = self.collection.distinct("ci_run_id", query)
        return list(result)

    def delete_by_repo_config(
        self, model_repo_config_id: ObjectId, session: ClientSession | None = None
    ) -> int:
        """
        Delete all import builds for a repo config.

        Args:
            model_repo_config_id: The ModelRepoConfig ID
            session: Optional MongoDB session for transaction support

        Returns:
            Number of documents deleted.
        """
        result = self.collection.delete_many(
            {"model_repo_config_id": model_repo_config_id},
            session=session,
        )
        return result.deleted_count
