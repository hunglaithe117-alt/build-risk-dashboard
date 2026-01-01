"""
DatasetImportBuild Repository - Database operations for dataset import builds.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.synchronous.client_session import ClientSession

from app.entities.dataset_import_build import (
    DatasetImportBuild,
    DatasetImportBuildStatus,
    ResourceStatus,
)
from app.repositories.base import BaseRepository

if TYPE_CHECKING:
    pass


class DatasetImportBuildRepository(BaseRepository[DatasetImportBuild]):
    """Repository for DatasetImportBuild operations."""

    def __init__(self, db):
        super().__init__(db, "dataset_import_builds", DatasetImportBuild)

    def find_by_version(
        self,
        version_id: str,
        status: Optional[DatasetImportBuildStatus] = None,
    ) -> List[DatasetImportBuild]:
        """
        Find all builds for a dataset version, optionally filtered by status.

        Args:
            version_id: DatasetVersion ID
            status: Optional status filter

        Returns:
            List of DatasetImportBuild entities
        """
        query = {"dataset_version_id": ObjectId(version_id)}
        if status:
            query["status"] = status.value if hasattr(status, "value") else status
        return self.find_many(query)

    def find_pending_builds(self, version_id: str) -> List[DatasetImportBuild]:
        """Find pending builds for ingestion."""
        return self.find_by_version(version_id, status=DatasetImportBuildStatus.PENDING)

    def find_ingesting_builds(self, version_id: str) -> List[DatasetImportBuild]:
        """Find builds currently ingesting."""
        return self.find_by_version(version_id, status=DatasetImportBuildStatus.INGESTING)

    def find_ingested_builds(self, version_id: str) -> List[DatasetImportBuild]:
        """Find successfully ingested builds."""
        return self.find_by_version(version_id, status=DatasetImportBuildStatus.INGESTED)

    def find_missing_resource_imports(self, version_id: str) -> List[DatasetImportBuild]:
        """Find builds with missing resources (not retryable - logs expired, etc)."""
        return self.find_by_version(version_id, status=DatasetImportBuildStatus.MISSING_RESOURCE)

    def find_failed_builds(self, version_id: str) -> List[DatasetImportBuild]:
        """Find builds with FAILED status (retryable - actual errors like timeout, network)."""
        return self.find_by_version(version_id, status=DatasetImportBuildStatus.FAILED)

    def count_by_status(self, version_id: str) -> dict:
        """
        Get count of builds by status for a dataset version.

        Returns:
            Dict mapping status -> count
        """
        pipeline = [
            {"$match": {"dataset_version_id": ObjectId(version_id)}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        results = list(self.collection.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in results}

    def update_many_by_status(
        self,
        version_id: str,
        from_status: str,
        updates: dict,
    ) -> int:
        """
        Update all builds with given status.

        Args:
            version_id: DatasetVersion ID
            from_status: Current status to filter
            updates: Fields to update

        Returns:
            Number of builds updated
        """
        result = self.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": from_status,
            },
            {"$set": updates},
        )
        return result.modified_count

    def bulk_insert(self, builds: List[DatasetImportBuild]) -> List[DatasetImportBuild]:
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
        version_id: str,
        dataset_build_id: str,
    ) -> Optional[DatasetImportBuild]:
        """Find by unique business key (version + dataset_build)."""
        return self.find_one(
            {
                "dataset_version_id": ObjectId(version_id),
                "dataset_build_id": ObjectId(dataset_build_id),
            }
        )

    def upsert_by_business_key(
        self,
        version_id: str,
        dataset_build_id: str,
        raw_repo_id: str,
        raw_build_run_id: str,
        status: DatasetImportBuildStatus,
        ci_run_id: str,
        commit_sha: str,
        repo_full_name: str = "",
    ) -> DatasetImportBuild:
        """
        Atomic upsert by business key (version + dataset_build).

        Uses atomic find_one_and_update for thread safety.
        This prevents duplicate records when the same task runs concurrently.
        """
        update_data = {
            "dataset_version_id": ObjectId(version_id),
            "dataset_build_id": ObjectId(dataset_build_id),
            "raw_repo_id": ObjectId(raw_repo_id),
            "raw_build_run_id": ObjectId(raw_build_run_id),
            "status": status.value if hasattr(status, "value") else status,
            "ci_run_id": ci_run_id,
            "commit_sha": commit_sha,
            "repo_full_name": repo_full_name,
        }

        doc = self.collection.find_one_and_update(
            {
                "dataset_version_id": ObjectId(version_id),
                "dataset_build_id": ObjectId(dataset_build_id),
            },
            {"$set": update_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return DatasetImportBuild(**doc)

    def find_by_raw_build_run_ids(
        self,
        version_id: str,
        raw_build_run_ids: List[str],
    ) -> List[DatasetImportBuild]:
        """Batch query: Find all import builds by their raw_build_run_ids."""
        if not raw_build_run_ids:
            return []

        oids = [ObjectId(rid) for rid in raw_build_run_ids if ObjectId.is_valid(rid)]
        if not oids:
            return []

        return self.find_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "raw_build_run_id": {"$in": oids},
            }
        )

    def find_by_dataset_build_ids(
        self,
        version_id: str,
        dataset_build_ids: List[str],
    ) -> List[DatasetImportBuild]:
        """Batch query: Find all import builds by their dataset_build_ids."""
        if not dataset_build_ids:
            return []

        oids = [ObjectId(bid) for bid in dataset_build_ids if ObjectId.is_valid(bid)]
        if not oids:
            return []

        return self.find_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "dataset_build_id": {"$in": oids},
            }
        )

    def get_commit_shas_by_repo(self, version_id: str, raw_repo_id: str) -> List[str]:
        """Get unique commit SHAs for a specific repo in version."""
        query = {
            "dataset_version_id": ObjectId(version_id),
            "raw_repo_id": ObjectId(raw_repo_id),
            "status": {
                "$in": [
                    DatasetImportBuildStatus.PENDING.value,
                    DatasetImportBuildStatus.INGESTING.value,
                ]
            },
        }
        result = self.collection.distinct("commit_sha", query)
        return [sha for sha in result if sha]

    def get_ci_run_ids_by_repo(self, version_id: str, raw_repo_id: str) -> List[str]:
        """Get CI run IDs for a specific repo in version."""
        query = {
            "dataset_version_id": ObjectId(version_id),
            "raw_repo_id": ObjectId(raw_repo_id),
            "status": {
                "$in": [
                    DatasetImportBuildStatus.PENDING.value,
                    DatasetImportBuildStatus.INGESTING.value,
                ]
            },
        }
        result = self.collection.distinct("ci_run_id", query)
        return list(result)

    def delete_by_version(self, version_id: str, session: ClientSession | None = None) -> int:
        """Delete all import builds for a dataset version."""
        result = self.collection.delete_many(
            {"dataset_version_id": ObjectId(version_id)},
            session=session,
        )
        return result.deleted_count

    def delete_by_dataset(
        self,
        dataset_id: ObjectId,
        session: ClientSession | None = None,
    ) -> int:
        """
        Delete all import builds for a dataset (across all versions).

        Performs a lookup via dataset_versions to find all version IDs,
        then deletes import builds for those versions.
        """
        # Find all version IDs for this dataset
        version_ids = list(
            self.db.dataset_versions.distinct(
                "_id",
                {"dataset_id": dataset_id},
            )
        )

        if not version_ids:
            return 0

        result = self.collection.delete_many(
            {"dataset_version_id": {"$in": version_ids}},
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
            build_id: DatasetImportBuild ID
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
        version_id: str,
        resource: str,
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> int:
        """
        Update resource status for all INGESTING builds in a version.

        Args:
            version_id: DatasetVersion ID
            resource: Resource name
            status: New status
            error: Optional error message

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

        result = self.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
            },
            {"$set": update},
        )
        return result.modified_count

    def update_resource_status_for_repo(
        self,
        version_id: str,
        raw_repo_id: str,
        resource: str,
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> int:
        """
        Update resource status for builds of a specific repo in version.

        Args:
            version_id: DatasetVersion ID
            raw_repo_id: RawRepository ID
            resource: Resource name
            status: New status
            error: Optional error message

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

        result = self.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "raw_repo_id": ObjectId(raw_repo_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
            },
            {"$set": update},
        )
        return result.modified_count

    def init_resource_status(
        self,
        version_id: str,
        required_resources: List[str],
    ) -> int:
        """
        Initialize resource_status for all PENDING builds.

        Sets required resources to PENDING and others to SKIPPED.

        Args:
            version_id: DatasetVersion ID
            required_resources: List of resource names needed

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
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.PENDING.value,
            },
            {
                "$set": {
                    "resource_status": resource_status,
                    "required_resources": required_resources,
                    "status": DatasetImportBuildStatus.INGESTING.value,
                    "ingestion_started_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count

    def mark_ingested_batch(self, version_id: str) -> int:
        """
        Mark all INGESTING builds as INGESTED.

        Call this after all resources are completed successfully.

        Returns:
            Number of builds updated
        """
        result = self.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
            },
            {
                "$set": {
                    "status": DatasetImportBuildStatus.INGESTED.value,
                    "ingested_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count

    def mark_missing_resource_by_resource(
        self,
        version_id: str,
        resource: str,
    ) -> int:
        """
        Mark builds as MISSING_RESOURCE if a specific resource failed.

        Args:
            version_id: DatasetVersion ID
            resource: Resource that failed

        Returns:
            Number of builds marked as missing resource
        """
        result = self.collection.update_many(
            {
                "dataset_version_id": ObjectId(version_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                f"resource_status.{resource}.status": ResourceStatus.FAILED.value,
            },
            {
                "$set": {
                    "status": DatasetImportBuildStatus.MISSING_RESOURCE.value,
                }
            },
        )
        return result.modified_count

    def find_by_missing_resource(
        self,
        version_id: str,
        resource: str,
    ) -> List[DatasetImportBuild]:
        """Find builds with a specific missing/failed resource."""
        return self.find_many(
            {
                "dataset_version_id": ObjectId(version_id),
                f"resource_status.{resource}.status": ResourceStatus.FAILED.value,
            }
        )

    def update_resource_by_commits(
        self,
        version_id: str,
        raw_repo_id: str,
        resource: str,
        failed_commits: List[str],
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> int:
        """
        Update resource status for builds matching specific commit SHAs.

        Args:
            version_id: DatasetVersion ID
            raw_repo_id: RawRepository ID
            resource: Resource name (e.g., git_worktree)
            failed_commits: List of commit SHAs that failed
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
                "dataset_version_id": ObjectId(version_id),
                "raw_repo_id": ObjectId(raw_repo_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "commit_sha": {"$in": failed_commits},
            },
            {"$set": update},
        )
        return result.modified_count

    def update_resource_by_ci_run_ids(
        self,
        version_id: str,
        raw_repo_id: str,
        resource: str,
        ci_run_ids: List[str],
        status: ResourceStatus,
        error: Optional[str] = None,
    ) -> int:
        """
        Update resource status for builds matching specific CI run IDs.

        Args:
            version_id: DatasetVersion ID
            raw_repo_id: RawRepository ID
            resource: Resource name (e.g., build_logs)
            ci_run_ids: List of CI run IDs
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
                "dataset_version_id": ObjectId(version_id),
                "raw_repo_id": ObjectId(raw_repo_id),
                "status": DatasetImportBuildStatus.INGESTING.value,
                "ci_run_id": {"$in": ci_run_ids},
            },
            {"$set": update},
        )
        return result.modified_count

    def get_resource_status_summary(self, version_id: str) -> dict:
        """
        Get aggregated resource status counts for a dataset version.

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
            {"$match": {"dataset_version_id": ObjectId(version_id)}},
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

    def get_progress_by_repo(self, version_id: str) -> List[dict]:
        """
        Get ingestion progress grouped by repository.

        Returns list of:
        {
            "raw_repo_id": ObjectId,
            "repo_full_name": str,
            "pending": int,
            "ingesting": int,
            "ingested": int,
            "failed": int,
            "total": int
        }
        """
        pipeline = [
            {"$match": {"dataset_version_id": ObjectId(version_id)}},
            {
                "$group": {
                    "_id": "$raw_repo_id",
                    "repo_full_name": {"$first": "$repo_full_name"},
                    "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
                    "ingesting": {"$sum": {"$cond": [{"$eq": ["$status", "ingesting"]}, 1, 0]}},
                    "ingested": {"$sum": {"$cond": [{"$eq": ["$status", "ingested"]}, 1, 0]}},
                    "missing_resource": {
                        "$sum": {"$cond": [{"$eq": ["$status", "missing_resource"]}, 1, 0]}
                    },
                    "total": {"$sum": 1},
                }
            },
        ]
        return list(self.collection.aggregate(pipeline))

    def list_by_version_with_details(
        self,
        version_id: ObjectId,
        skip: int = 0,
        limit: int = 20,
        status_filter: Optional[str] = None,
    ) -> tuple[list, int]:
        """
        List import builds for a version with RawBuildRun details.

        Uses MongoDB aggregation to join with raw_build_runs collection.

        Returns:
            Tuple of (list of build dicts with RawBuildRun data, total count)
        """
        match_query: dict = {"dataset_version_id": version_id}
        if status_filter:
            match_query["status"] = status_filter

        # Count total first
        total = self.collection.count_documents(match_query)

        # Build aggregation pipeline
        pipeline = [
            {"$match": match_query},
            {"$sort": {"created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            # Join with raw_build_runs to get CI build details
            {
                "$lookup": {
                    "from": "raw_build_runs",
                    "localField": "raw_build_run_id",
                    "foreignField": "_id",
                    "as": "raw_build_run",
                }
            },
            {"$unwind": {"path": "$raw_build_run", "preserveNullAndEmptyArrays": True}},
            # Project final shape
            {
                "$project": {
                    "_id": 1,
                    "dataset_version_id": 1,
                    "raw_build_run_id": 1,
                    "raw_repo_id": 1,
                    "status": 1,
                    "resource_status": 1,
                    "required_resources": 1,
                    "ingested_at": 1,
                    "created_at": 1,
                    "ingestion_error": 1,
                    # From RawBuildRun
                    "ci_run_id": "$raw_build_run.ci_run_id",
                    "build_number": "$raw_build_run.build_number",
                    "commit_sha": "$raw_build_run.commit_sha",
                    "branch": "$raw_build_run.branch",
                    "conclusion": "$raw_build_run.conclusion",
                    "web_url": "$raw_build_run.web_url",
                    # Additional RawBuildRun fields for detailed view
                    "commit_message": "$raw_build_run.commit_message",
                    "commit_author": "$raw_build_run.commit_author",
                    "duration_seconds": "$raw_build_run.duration_seconds",
                    "started_at": "$raw_build_run.started_at",
                    "completed_at": "$raw_build_run.completed_at",
                    "provider": "$raw_build_run.provider",
                    "logs_available": "$raw_build_run.logs_available",
                    "logs_expired": "$raw_build_run.logs_expired",
                }
            },
        ]

        results = list(self.collection.aggregate(pipeline))
        return results, total
