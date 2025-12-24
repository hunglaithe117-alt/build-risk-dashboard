from __future__ import annotations

from typing import Optional

from pymongo.client_session import ClientSession
from pymongo.database import Database

from app.entities.dataset_build import DatasetBuild

from .base import BaseRepository


class DatasetBuildRepository(BaseRepository[DatasetBuild]):
    """Repository for dataset_builds collection."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_builds", DatasetBuild)

    def find_existing(
        self, dataset_id, build_id_from_csv: str, raw_repo_id
    ) -> Optional[DatasetBuild]:
        """Find a build by dataset, CSV build id, and raw repo id."""
        return self.find_one(
            {
                "dataset_id": self._to_object_id(dataset_id),
                "build_id_from_csv": build_id_from_csv,
                "raw_repo_id": self._to_object_id(raw_repo_id),
            }
        )

    def delete_by_dataset(self, dataset_id: str, session: "ClientSession | None" = None) -> int:
        """Delete all builds for a dataset.

        Args:
            dataset_id: Dataset ID to delete builds for
            session: Optional MongoDB session for transaction support
        """
        oid = self._to_object_id(dataset_id)
        if not oid:
            return 0
        return self.delete_many({"dataset_id": oid}, session=session)

    def find_validated_builds(self, dataset_id: str) -> list[DatasetBuild]:
        """Find all validated builds (status=FOUND) for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return []
        return self.find_many({"dataset_id": oid, "status": "found"})

    def find_found_builds_by_repo(self, dataset_id: str, raw_repo_id: str) -> list[DatasetBuild]:
        """Find found builds for a specific raw repo in a dataset."""
        oid_ds = self._to_object_id(dataset_id)
        oid_repo = self._to_object_id(raw_repo_id)
        if not oid_ds or not oid_repo:
            return []
        return self.find_many({"dataset_id": oid_ds, "raw_repo_id": oid_repo, "status": "found"})

    def find_builds_with_run_ids(self, dataset_id: str) -> list[DatasetBuild]:
        """Find all validated builds with ci_run_id populated."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return []
        return self.find_many(
            {
                "dataset_id": oid,
                "status": "found",
                "ci_run_id": {"$ne": None},
            }
        )

    def count_by_query(self, query: dict) -> int:
        """Count documents matching the query."""
        return self.count(query)

    def find_by_query(
        self,
        query: dict,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "validated_at",
        sort_order: int = -1,
    ) -> list[DatasetBuild]:
        """Find builds matching query with pagination and sorting."""
        return self.find_many(query, sort=[(sort_by, sort_order)], skip=skip, limit=limit)

    def get_validated_repo_names(self, dataset_id: str) -> list[dict]:
        """Get unique validated repo names using MongoDB aggregation.

        Returns list of dicts with repo_name, builds_in_csv, builds_found.
        Only includes repos that have at least one 'found' build.
        """
        oid = self._to_object_id(dataset_id)
        if not oid:
            return []

        pipeline = [
            {"$match": {"dataset_id": oid}},
            {
                "$group": {
                    "_id": "$repo_name_from_csv",
                    "builds_in_csv": {"$sum": 1},
                    "builds_found": {"$sum": {"$cond": [{"$eq": ["$status", "found"]}, 1, 0]}},
                }
            },
            # Only repos with at least one found build
            {"$match": {"builds_found": {"$gt": 0}}},
            {"$sort": {"_id": 1}},
            {
                "$project": {
                    "_id": 0,
                    "repo_name": "$_id",
                    "builds_in_csv": 1,
                    "builds_found": 1,
                    "validation_status": {"$literal": "valid"},
                }
            },
        ]

        return list(self.collection.aggregate(pipeline))

    def iterate_builds_with_run_ids_paginated(
        self,
        dataset_id: str,
        batch_size: int = 1000,
    ):
        """
        Iterate validated builds with ci_run_id using cursor pagination.

        Yields batches of builds to avoid loading all into memory.
        Uses _id-based cursor pagination for efficiency with large datasets.

        Args:
            dataset_id: Dataset ID to query
            batch_size: Number of builds per batch

        Yields:
            List[DatasetBuild]: Batches of builds
        """
        oid = self._to_object_id(dataset_id)
        if not oid:
            return

        base_query = {
            "dataset_id": oid,
            "status": "found",
            "ci_run_id": {"$ne": None},
        }

        last_id = None
        while True:
            query = base_query.copy()
            if last_id:
                query["_id"] = {"$gt": last_id}

            # Fetch batch with _id sort for cursor pagination
            cursor = self.collection.find(query).sort("_id", 1).limit(batch_size)
            batch = [DatasetBuild(**doc) for doc in cursor]

            if not batch:
                break

            yield batch
            last_id = batch[-1].id
