"""Repository for dataset templates (seeded datasets shared by all users)."""

from pymongo.database import Database

from app.entities.dataset_template import DatasetTemplate
from .base import BaseRepository


class DatasetTemplateRepository(BaseRepository[DatasetTemplate]):
    """MongoDB repository for dataset templates."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_templates", DatasetTemplate)
