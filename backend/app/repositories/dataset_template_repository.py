"""Repository for dataset templates (seeded datasets shared by all users)."""

from typing import Optional

from pymongo.database import Database

from app.entities.dataset_template import DatasetTemplate

from .base import BaseRepository


class DatasetTemplateRepository(BaseRepository[DatasetTemplate]):
    """MongoDB repository for dataset templates."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_templates", DatasetTemplate)

    def find_by_name(self, name: str) -> Optional[DatasetTemplate]:
        """Find template by exact name."""
        return self.find_one({"name": name})
