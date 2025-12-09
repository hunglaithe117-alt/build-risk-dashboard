"""Model Build repository for database operations."""

from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.entities.model_build import ModelBuild
from .base import BaseRepository


class ModelBuildRepository(BaseRepository[ModelBuild]):
    """Repository for ModelBuild entities (Model training flow)."""

    def __init__(self, db: Database):
        super().__init__(db, "model_builds", ModelBuild)

    def find_by_repo_and_run_id(
        self, repo_id: str, workflow_run_id: int
    ) -> Optional[ModelBuild]:
        """Find a build by repo and workflow run ID."""
        return self.find_one(
            {
                "repo_id": self._to_object_id(repo_id),
                "workflow_run_id": workflow_run_id,
            }
        )

    def list_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 0
    ) -> tuple[List[ModelBuild], int]:
        """List builds for a model repository with pagination."""
        return self.paginate(
            {"repo_id": self._to_object_id(repo_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )
