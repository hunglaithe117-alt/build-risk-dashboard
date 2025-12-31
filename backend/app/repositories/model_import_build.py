"""
ModelImportBuild Repository - Database operations for model import builds.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.synchronous.client_session import ClientSession

from app.entities.model_import_build import (
    ModelImportBuild,
    ModelImportBuildStatus,
    ResourceStatus,
)
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    pass


class ModelImportBuildRepository(BaseRepository[ModelImportBuild]):
    """Repository for ModelImportBuild operations."""

    def __init__(self, db):
        super().__init__(db, "model_import_builds", ModelImportBuild)

    def find_by_repo_config(
        self,
        config_id: str,
        status: Optional[ModelImportBuildStatus] = None,
    ) -> List[ModelImportBuild]:
        """
        Find all builds for a repo config, optionally filtered by status.

        Args:
            config_id: ModelRepoConfig ID
            status: Optional status filter

        Returns:
            List of ModelImportBuild entities
        """
        query = {"model_repo_config_id": ObjectId(config_id)}
        if status:
            query["status"] = status.value if hasattr(status, "value") else status
        return self.find_many(query)

    def find_unprocessed_builds(
        self,
        config_id: str,
        after_id: Optional[ObjectId] = None,
        include_failed: bool = False,
    ) -> List[ModelImportBuild]:
        """
        Find builds that haven't been processed yet.

        Uses ObjectId comparison which is more reliable than timestamp
        since ObjectId embeds creation time and auto-increments.

        Args:
            config_id: ModelRepoConfig ID
            after_id: Only return builds with _id > after_id (checkpoint)
            include_failed: If True, include FAILED builds along with INGESTED

        Returns:
            List of ModelImportBuild entities after checkpoint, sorted by _id ascending
        """
        query = {
            "model_repo_config_id": ObjectId(config_id),
        }

        # Include both INGESTED and FAILED if requested (graceful failure handling)
        if include_failed:
            query["status"] = {
                "$in": [
                    ModelImportBuildStatus.INGESTED.value,
                    ModelImportBuildStatus.MISSING_RESOURCE.value,
                ]
            }
        else:
            query["status"] = ModelImportBuildStatus.INGESTED.value

        if after_id:
            query["_id"] = {"$gt": after_id}

        # Sort by _id ascending to process in insertion order
        docs = list(self.collection.find(query).sort("_id", 1))
        return [ModelImportBuild(**doc) for doc in docs]

    def find_fetched_builds(self, config_id: str) -> List[ModelImportBuild]:
        """Find successfully fetched builds."""
        return self.find_by_repo_config(config_id, status=ModelImportBuildStatus.FETCHED)

    def find_missing_resource_builds(
        self, config_id: str, after_id: Optional[ObjectId] = None
    ) -> List[ModelImportBuild]:
        """Find builds with missing resources for retry.

        Args:
            config_id: ModelRepoConfig ID
            after_id: Only return builds with _id > after_id (for checkpoint filtering)
        """
        query = {
            "model_repo_config_id": ObjectId(config_id),
            "status": ModelImportBuildStatus.MISSING_RESOURCE.value,
        }
        if after_id:
            query["_id"] = {"$gt": after_id}
        return self.find_many(query)

    def get_missing_resource_builds_with_errors(
        self, config_id: str, limit: int = 50
    ) -> List[dict]:
        """
        Get builds with missing resources and error details for UI display.

        Returns list of dicts with:
        - ci_run_id, commit_sha, status
        - ingestion_error (general error)
        - resource_errors (per-resource errors)
        """
        pipeline = [
            {
                "$match": {
                    "model_repo_config_id": ObjectId(config_id),
                    "status": ModelImportBuildStatus.MISSING_RESOURCE.value,
                }
            },
            {"$limit": limit},
            {
                "$project": {
                    "_id": 1,
                    "ci_run_id": 1,
                    "commit_sha": 1,
                    "status": 1,
                    "ingestion_error": 1,
                    "resource_status": 1,
                    "fetched_at": 1,
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))

        # Transform to extract error messages
        failed_builds = []
        for doc in results:
            resource_errors = {}
            for res_name, res_data in (doc.get("resource_status") or {}).items():
                if isinstance(res_data, dict) and res_data.get("status") == "failed":
                    resource_errors[res_name] = res_data.get("error", "Unknown error")

            failed_builds.append(
                {
                    "id": str(doc["_id"]),
                    "ci_run_id": doc.get("ci_run_id"),
                    "commit_sha": doc.get("commit_sha", "")[:8],
                    "status": doc.get("status"),
                    "ingestion_error": doc.get("ingestion_error"),
                    "resource_errors": resource_errors,
                    "fetched_at": doc.get("fetched_at"),
                }
            )

        return failed_builds

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

    def update_many_by_status(
        self,
        config_id: str,
        from_status: str,
        updates: dict,
    ) -> int:
        """
        Update all builds with given status.

        Args:
            config_id: ModelRepoConfig ID
            from_status: Current status to filter
            updates: Fields to update

        Returns:
            Number of builds updated
        """
        result = self.collection.update_many(
            {
                "model_repo_config_id": ObjectId(config_id),
                "status": from_status,
            },
            {"$set": updates},
        )
        return result.modified_count

    def bulk_insert(self, builds: List[ModelImportBuild]) -> List[ModelImportBuild]:
        """Insert multiple builds in one operation."""
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

    def upsert_by_business_key(
        self,
        config_id: str,
        raw_build_run_id: str,
        status: ModelImportBuildStatus,
        ci_run_id: str,
        commit_sha: str,
    ) -> ModelImportBuild:
        """
        Atomic upsert by business key (config + raw_build_run).

        Uses atomic find_one_and_update for thread safety.
        This prevents duplicate records when the same task runs concurrently.
        """
        update_data = {
            "model_repo_config_id": ObjectId(config_id),
            "raw_build_run_id": ObjectId(raw_build_run_id),
            "status": status.value if hasattr(status, "value") else status,
            "ci_run_id": ci_run_id,
            "commit_sha": commit_sha,
        }

        doc = self.collection.find_one_and_update(
            {
                "model_repo_config_id": ObjectId(config_id),
                "raw_build_run_id": ObjectId(raw_build_run_id),
            },
            {"$set": update_data, "$setOnInsert": {"created_at": ObjectId().generation_time}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return ModelImportBuild(**doc)

    def find_by_raw_build_run_ids(
        self,
        config_id: str,
        raw_build_run_ids: List[str],
    ) -> List[ModelImportBuild]:
        """Batch query: Find all import builds by their raw_build_run_ids."""
        if not raw_build_run_ids:
            return []

        oids = [ObjectId(rid) for rid in raw_build_run_ids if ObjectId.is_valid(rid)]
        if not oids:
            return []

        return self.find_many(
            {
                "model_repo_config_id": ObjectId(config_id),
                "raw_build_run_id": {"$in": oids},
            }
        )

    def get_commit_shas(self, config_id: str) -> List[str]:
        """Get unique commit SHAs for ingestion."""
        query = {
            "model_repo_config_id": ObjectId(config_id),
            "status": ModelImportBuildStatus.FETCHED.value,
        }
        result = self.collection.distinct("commit_sha", query)
        return [sha for sha in result if sha]

    def get_ci_run_ids(self, config_id: str) -> List[str]:
        """Get CI run IDs for log download."""
        query = {
            "model_repo_config_id": ObjectId(config_id),
            "status": ModelImportBuildStatus.FETCHED.value,
        }
        result = self.collection.distinct("ci_run_id", query)
        return list(result)

    def delete_by_repo_config(
        self, model_repo_config_id: ObjectId, session: ClientSession | None = None
    ) -> int:
        """Delete all import builds for a repo config."""
        result = self.collection.delete_many(
            {"model_repo_config_id": model_repo_config_id},
            session=session,
        )
        return result.deleted_count

    # ========== Resource Status Tracking Methods ==========

    def update_resource_status(
        self,
        build_id: str,
        resource: str,
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> bool:
        """
        Update status for a specific resource on a build.

        Args:
            build_id: ModelImportBuild ID
            resource: Resource name (e.g., 'clone', 'worktree', 'logs')
            status: New status
            error: Optional error message

        Returns:
            True if updated successfully
        """
        now = datetime.utcnow()
        update: dict = {
            f"resource_status.{resource}.status": status.value,
        }

        if error:
            update[f"resource_status.{resource}.error"] = error

        if status == ResourceStatus.COMPLETED:
            update[f"resource_status.{resource}.completed_at"] = now
        elif status == ResourceStatus.IN_PROGRESS:
            update[f"resource_status.{resource}.started_at"] = now

        result = self.collection.update_one(
            {"_id": ObjectId(build_id)},
            {"$set": update},
        )
        return result.modified_count > 0

    def update_resource_status_batch(
        self,
        config_id: str,
        resource: str,
        status: ResourceStatus,
        error: Optional[str] = None,
        from_resource_status: Optional[ResourceStatus] = None,
    ) -> int:
        """
        Update resource status for all INGESTING builds in a repo config.

        Args:
            config_id: ModelRepoConfig ID
            resource: Resource name
            status: New status
            error: Optional error message
            from_resource_status: Optional filter to only update if currently in this status

        Returns:
            Number of builds updated
        """
        now = datetime.utcnow()
        update: dict = {
            f"resource_status.{resource}.status": status.value,
        }

        if error:
            update[f"resource_status.{resource}.error"] = error

        if status == ResourceStatus.COMPLETED:
            update[f"resource_status.{resource}.completed_at"] = now
        elif status == ResourceStatus.IN_PROGRESS:
            update[f"resource_status.{resource}.started_at"] = now

        query = {
            "model_repo_config_id": ObjectId(config_id),
            "status": ModelImportBuildStatus.INGESTING.value,
        }

        # Add logic to query specific resource status if provided
        if from_resource_status:
            query[f"resource_status.{resource}.status"] = from_resource_status.value

        result = self.collection.update_many(
            query,
            {"$set": update},
        )
        return result.modified_count

    def init_resource_status(
        self,
        config_id: str,
        required_resources: List[str],
    ) -> int:
        """
        Initialize resource_status for all INGESTING builds.

        Sets required resources to PENDING and others to SKIPPED.

        Args:
            config_id: ModelRepoConfig ID
            required_resources: List of resource names needed by template

        Returns:
            Number of builds updated
        """
        from app.tasks.pipeline.shared.resources import FeatureResource

        # Get all ingestion-related resources from FeatureResource enum
        ingestion_resources = [
            FeatureResource.GIT_HISTORY.value,  # "git_history"
            FeatureResource.GIT_WORKTREE.value,  # "git_worktree"
            FeatureResource.BUILD_LOGS.value,  # "build_logs"
        ]

        # Build initial resource_status dict
        resource_status = {}
        for res in ingestion_resources:
            if res in required_resources:
                resource_status[res] = {
                    "status": ResourceStatus.PENDING.value,
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                }
            else:
                resource_status[res] = {
                    "status": ResourceStatus.SKIPPED.value,
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                }

        result = self.collection.update_many(
            {
                "model_repo_config_id": ObjectId(config_id),
                "status": ModelImportBuildStatus.INGESTING.value,
            },
            {
                "$set": {
                    "resource_status": resource_status,
                    "required_resources": required_resources,
                }
            },
        )
        return result.modified_count

    def find_by_failed_resource(
        self,
        config_id: str,
        resource: str,
    ) -> List[ModelImportBuild]:
        """Find builds with a specific failed resource."""
        return self.find_many(
            {
                "model_repo_config_id": ObjectId(config_id),
                f"resource_status.{resource}.status": ResourceStatus.FAILED.value,
            }
        )

    def update_resource_by_commits(
        self,
        config_id: str,
        resource: str,
        commits: List[str],
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> int:
        """
        Update resource status for builds matching specific commit SHAs.

        Args:
            config_id: ModelRepoConfig ID
            resource: Resource name (e.g., git_worktree)
            commits: List of commit SHAs that failed
            status: Status for failed builds
            error: Error message

        Returns:
            Number of builds updated
        """
        now = datetime.utcnow()
        update: dict = {
            f"resource_status.{resource}.status": status.value,
            f"resource_status.{resource}.completed_at": now,
        }
        if error:
            update[f"resource_status.{resource}.error"] = error

        result = self.collection.update_many(
            {
                "model_repo_config_id": ObjectId(config_id),
                "status": ModelImportBuildStatus.INGESTING.value,
                "commit_sha": {"$in": commits},
            },
            {"$set": update},
        )
        return result.modified_count

    def update_resource_by_ci_run_ids(
        self,
        config_id: str,
        resource: str,
        ci_run_ids: List[str],
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> int:
        """
        Update resource status for builds matching specific CI run IDs.

        Args:
            config_id: ModelRepoConfig ID
            resource: Resource name (e.g., build_logs)
            ci_run_ids: List of CI run IDs (e.g., GitHub Actions run IDs)
            status: Status for builds
            error: Error message

        Returns:
            Number of builds updated
        """
        now = datetime.utcnow()
        update: dict = {
            f"resource_status.{resource}.status": status.value,
            f"resource_status.{resource}.completed_at": now,
        }
        if error:
            update[f"resource_status.{resource}.error"] = error

        result = self.collection.update_many(
            {
                "model_repo_config_id": ObjectId(config_id),
                "status": ModelImportBuildStatus.INGESTING.value,
                "ci_run_id": {"$in": ci_run_ids},
            },
            {"$set": update},
        )
        return result.modified_count

    def get_resource_status_summary(self, config_id: str) -> dict:
        """
        Get aggregated resource status counts for a repo config.

        Returns structure like:
        {
            "git_history": {"completed": 10, "failed": 2},
            "git_worktree": {"completed": 8, "failed": 4},
            "build_logs": {"completed": 5, "skipped": 6}
        }
        """
        from app.tasks.pipeline.shared.resources import FeatureResource

        ingestion_resources = [
            FeatureResource.GIT_HISTORY.value,
            FeatureResource.GIT_WORKTREE.value,
            FeatureResource.BUILD_LOGS.value,
        ]

        # Build dynamic projection
        project_fields = {}
        facet_fields = {}
        for res in ingestion_resources:
            field_name = res.replace(".", "_") + "_status"
            project_fields[field_name] = f"$resource_status.{res}.status"
            facet_fields[res] = [
                {"$group": {"_id": f"${field_name}", "count": {"$sum": 1}}},
            ]

        pipeline = [
            {"$match": {"model_repo_config_id": ObjectId(config_id)}},
            {"$project": project_fields},
            {"$facet": facet_fields},
        ]

        results = list(self.collection.aggregate(pipeline))
        if not results:
            return {}

        facets = results[0]
        summary = {}

        for resource in ingestion_resources:
            summary[resource] = {}
            for item in facets.get(resource, []):
                if item["_id"]:
                    summary[resource][item["_id"]] = item["count"]

        return summary
