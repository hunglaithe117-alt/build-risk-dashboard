from typing import Optional

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

    def delete_by_dataset(self, dataset_id: str) -> int:
        """Delete all builds for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return 0
        return self.delete_many({"dataset_id": oid})

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
        """Find all validated builds with workflow_run_id populated."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return []
        return self.find_many(
            {
                "dataset_id": oid,
                "status": "found",
                "workflow_run_id": {"$ne": None},
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
