"""Repository for DatasetRepoConfig entities."""

from typing import List

from bson import ObjectId
from pymongo.database import Database

from app.entities.dataset_repo_config import DatasetRepoConfig
from app.repositories.base import BaseRepository


class DatasetRepoConfigRepository(BaseRepository[DatasetRepoConfig]):
    """Repository for DatasetRepoConfig - repos within a dataset."""

    def __init__(self, db: Database) -> None:
        super().__init__(db, "dataset_repo_configs", DatasetRepoConfig)

    def list_by_dataset(
        self,
        dataset_id: ObjectId,
        validation_status: str | None = None,
    ) -> List[DatasetRepoConfig]:
        """List repos for a dataset, sorted by name."""
        query = {"dataset_id": dataset_id}
        if validation_status:
            query["validation_status"] = validation_status

        return self.find_many(
            query,
            sort=[("full_name", 1)],
        )

    def count_by_dataset(self, dataset_id: ObjectId) -> int:
        """Count repos in a dataset."""
        return self.count({"dataset_id": dataset_id})

    def find_by_dataset_and_name(
        self,
        dataset_id: ObjectId,
        repo_name: str,
    ) -> DatasetRepoConfig | None:
        """Find a specific repo config by dataset and name."""
        return self.find_one(
            {
                "dataset_id": dataset_id,
                "full_name": repo_name,
            }
        )
