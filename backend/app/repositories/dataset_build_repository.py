from typing import Optional

from pymongo.database import Database

from app.entities.dataset_build import DatasetBuild
from .base import BaseRepository


class DatasetBuildRepository(BaseRepository[DatasetBuild]):
    """Repository for dataset_builds collection."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_builds", DatasetBuild)

    def find_existing(
        self, dataset_id, build_id_from_csv: str, repo_id
    ) -> Optional[DatasetBuild]:
        """Find a build by dataset, CSV build id, and repo."""
        return self.find_one(
            {
                "dataset_id": self._to_object_id(dataset_id),
                "build_id_from_csv": build_id_from_csv,
                "repo_id": self._to_object_id(repo_id),
            }
        )

    def delete_by_dataset(self, dataset_id) -> int:
        """Delete all builds for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return 0
        return self.delete_many({"dataset_id": oid})

    def find_validated_builds(self, dataset_id) -> list[DatasetBuild]:
        """Find all validated builds (status=FOUND) for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return []
        return self.find_many({"dataset_id": oid, "status": "found"})
