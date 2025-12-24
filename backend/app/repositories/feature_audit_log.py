"""
Feature Audit Log Repository - Database operations for feature extraction audit logs.
"""

from typing import Any, Dict, List, Optional, Tuple

from app.entities.feature_audit_log import AuditLogCategory, FeatureAuditLog

from .base import BaseRepository


class FeatureAuditLogRepository(BaseRepository[FeatureAuditLog]):
    """Repository for FeatureAuditLog entities."""

    def __init__(self, db):
        super().__init__(db, "feature_audit_logs", FeatureAuditLog)

    def find_recent(
        self,
        limit: int = 50,
        skip: int = 0,
        status: Optional[str] = None,
    ) -> Tuple[List[FeatureAuditLog], int]:
        """
        Find recent audit logs with optional status filter.

        Args:
            limit: Maximum number of logs to return
            skip: Number of logs to skip (for pagination)
            status: Optional status filter

        Returns:
            Tuple of (list of logs, total count)
        """
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status

        return self.paginate(
            query,
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_by_repo(
        self,
        raw_repo_id: str,
        limit: int = 20,
    ) -> List[FeatureAuditLog]:
        """Find recent audit logs for a specific repository."""
        return self.find_many(
            {"raw_repo_id": self._to_object_id(raw_repo_id)},
            sort=[("created_at", -1)],
            limit=limit,
        )

    def delete_by_raw_repo_id(self, raw_repo_id, category: AuditLogCategory, session=None) -> int:
        result = self.collection.delete_many(
            {
                "raw_repo_id": self._to_object_id(raw_repo_id),
                "category": category.value,
            },
            session=session,
        )
        return result.deleted_count

    def delete_by_version_id(self, version_id: str, session=None) -> int:
        """Delete all audit logs for a specific dataset version."""
        result = self.collection.delete_many(
            {"version_id": self._to_object_id(version_id)},
            session=session,
        )
        return result.deleted_count

    def delete_by_dataset_id(self, dataset_id: str, session=None) -> int:
        """Delete all audit logs for a specific dataset."""
        result = self.collection.delete_many(
            {"dataset_id": self._to_object_id(dataset_id)},
            session=session,
        )
        return result.deleted_count

    def find_by_build(self, raw_build_run_id: str) -> Optional[FeatureAuditLog]:
        """Find an audit log by raw build run ID."""
        return self.find_one({"raw_build_run_id": self._to_object_id(raw_build_run_id)})

    def find_by_enrichment_build(self, enrichment_build_id: str) -> Optional[FeatureAuditLog]:
        """Find an audit log by enrichment build ID."""
        return self.find_one({"enrichment_build_id": self._to_object_id(enrichment_build_id)})

    def find_by_training_build(self, training_build_id: str) -> Optional[FeatureAuditLog]:
        """Find an audit log by training build ID."""
        return self.find_one({"training_build_id": self._to_object_id(training_build_id)})

    def find_recent_cursor(
        self,
        limit: int = 20,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[FeatureAuditLog], Optional[str], bool]:
        """
        Find recent audit logs with cursor-based pagination.

        Args:
            limit: Maximum number of logs to return
            cursor: Last item ID from previous page (fetch items older than this)
            status: Optional status filter

        Returns:
            Tuple of (list of logs, next_cursor, has_more)
        """
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status

        # If cursor provided, get items with _id less than cursor (older)
        if cursor:
            query["_id"] = {"$lt": self._to_object_id(cursor)}

        # Fetch limit + 1 to check if there are more items
        logs = self.find_many(
            query,
            sort=[("_id", -1)],  # Sort by _id descending (newest first)
            limit=limit + 1,
        )

        has_more = len(logs) > limit
        if has_more:
            logs = logs[:limit]  # Remove the extra item

        next_cursor = str(logs[-1].id) if logs and has_more else None

        return logs, next_cursor, has_more

    def find_by_version(
        self,
        version_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[FeatureAuditLog], int]:
        """Find audit logs for a specific dataset version."""

        # Find all enrichment builds for this version, then get their audit logs
        query = {"enrichment_build_id": {"$exists": True}}
        return self.paginate(
            query,
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_by_dataset_cursor(
        self,
        dataset_id: str,
        limit: int = 20,
        cursor: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[FeatureAuditLog], Optional[str], bool]:
        """
        Find audit logs for a specific dataset with cursor-based pagination.

        This queries through the chain: FeatureAuditLog.enrichment_build_id
        → DatasetEnrichmentBuild.version_id → DatasetVersion.dataset_id

        Args:
            dataset_id: The dataset ID to filter by
            limit: Maximum number of logs to return
            cursor: Last item ID from previous page
            status: Optional status filter

        Returns:
            Tuple of (list of logs, next_cursor, has_more)
        """
        # Step 1: Get all version IDs for this dataset
        version_ids = [
            doc["_id"]
            for doc in self.db["dataset_versions"].find(
                {"dataset_id": self._to_object_id(dataset_id)},
                {"_id": 1},
            )
        ]

        if not version_ids:
            return [], None, False

        # Step 2: Get all enrichment build IDs for these versions
        enrichment_build_ids = [
            doc["_id"]
            for doc in self.db["dataset_enrichment_builds"].find(
                {"version_id": {"$in": version_ids}},
                {"_id": 1},
            )
        ]

        if not enrichment_build_ids:
            return [], None, False

        # Step 3: Query audit logs with these enrichment build IDs
        query: Dict[str, Any] = {"enrichment_build_id": {"$in": enrichment_build_ids}}

        if status:
            query["status"] = status

        if cursor:
            query["_id"] = {"$lt": self._to_object_id(cursor)}

        # Fetch limit + 1 to check if there are more items
        logs = self.find_many(
            query,
            sort=[("_id", -1)],
            limit=limit + 1,
        )

        has_more = len(logs) > limit
        if has_more:
            logs = logs[:limit]

        next_cursor = str(logs[-1].id) if logs and has_more else None

        return logs, next_cursor, has_more
