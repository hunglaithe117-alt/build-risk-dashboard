from typing import List, Optional

from pymongo.database import Database

from app.entities.dataset_repo_stats import DatasetRepoStats
from app.repositories.base import BaseRepository


class DatasetRepoStatsRepository(BaseRepository[DatasetRepoStats]):
    """Repository for DatasetRepoStats entity."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_repo_stats", DatasetRepoStats)

    def find_by_dataset(self, dataset_id: str) -> List[DatasetRepoStats]:
        """Get all repo stats for a dataset."""
        return self.find_many({"dataset_id": self._to_object_id(dataset_id)})

    def find_by_dataset_and_repo(
        self, dataset_id: str, raw_repo_id: str
    ) -> Optional[DatasetRepoStats]:
        """Get stats for specific repo in dataset."""
        return self.find_one(
            {
                "dataset_id": self._to_object_id(dataset_id),
                "raw_repo_id": self._to_object_id(raw_repo_id),
            }
        )

    def upsert_by_dataset_and_repo(
        self, dataset_id: str, raw_repo_id: str, **data
    ) -> Optional[DatasetRepoStats]:
        """Create or update repo stats."""
        query = {
            "dataset_id": self._to_object_id(dataset_id),
            "raw_repo_id": self._to_object_id(raw_repo_id),
        }
        update_data = {**query, **data}
        return self.find_one_and_update(
            query=query,
            update={"$set": update_data},
            upsert=True,
        )

    def delete_by_dataset(self, dataset_id: str) -> int:
        """Delete all repo stats for a dataset."""
        return self.delete_many({"dataset_id": self._to_object_id(dataset_id)})
