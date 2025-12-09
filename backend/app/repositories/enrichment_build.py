"""Enrichment Build repository for database operations."""

from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.entities.enrichment_build import EnrichmentBuild
from .base import BaseRepository


class EnrichmentBuildRepository(BaseRepository[EnrichmentBuild]):
    """Repository for EnrichmentBuild entities (Dataset enrichment flow)."""

    def __init__(self, db: Database):
        super().__init__(db, "enrichment_builds", EnrichmentBuild)
        # Index on dataset_id for fast lookups
        self.collection.create_index("dataset_id", background=True)
        self.collection.create_index("enrichment_repo_id", background=True)

    def find_by_build_id_and_dataset(
        self, build_id: str, dataset_id: str
    ) -> Optional[EnrichmentBuild]:
        """Find a build by build_id and dataset."""
        return self.find_one(
            {
                "build_id": build_id,
                "dataset_id": self._to_object_id(dataset_id),
            }
        )

    def find_by_build_id_and_repo(
        self, build_id: str, enrichment_repo_id: str
    ) -> Optional[EnrichmentBuild]:
        """Find a build by build_id and enrichment repo."""
        return self.find_one(
            {
                "build_id": build_id,
                "enrichment_repo_id": self._to_object_id(enrichment_repo_id),
            }
        )

    def list_by_dataset(
        self, dataset_id: str, skip: int = 0, limit: int = 0
    ) -> tuple[List[EnrichmentBuild], int]:
        """List builds for a dataset with pagination."""
        return self.paginate(
            {"dataset_id": self._to_object_id(dataset_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )

    def list_by_repo(
        self, enrichment_repo_id: str, skip: int = 0, limit: int = 0
    ) -> tuple[List[EnrichmentBuild], int]:
        """List builds for an enrichment repository with pagination."""
        return self.paginate(
            {"enrichment_repo_id": self._to_object_id(enrichment_repo_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )
