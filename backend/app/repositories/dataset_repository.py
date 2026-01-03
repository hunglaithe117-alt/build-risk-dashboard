"""Repository for dataset/project metadata."""

from typing import Any, Dict, Optional

from pymongo.database import Database

from app.entities.dataset import DatasetProject

from .base import BaseRepository


class DatasetRepository(BaseRepository[DatasetProject]):
    """MongoDB repository for datasets uploaded by users."""

    def __init__(self, db: Database):
        super().__init__(db, "datasets", DatasetProject)

    def list_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 0,
        q: Optional[str] = None,
    ) -> tuple[list[DatasetProject], int]:
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = self._to_object_id(user_id)

        if q:
            query["$or"] = [
                {"name": {"$regex": q, "$options": "i"}},
                {"file_name": {"$regex": q, "$options": "i"}},
            ]

        return self.paginate(
            query,
            sort=[("updated_at", -1), ("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def count_by_filter(self, user_id: Optional[str] = None) -> int:
        """
        Count datasets with optional user filter.

        Args:
            user_id: Optional user ID to filter by (admin sees all if None)

        Returns:
            Number of datasets matching the filter
        """
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = self._to_object_id(user_id)
        return self.collection.count_documents(query)
