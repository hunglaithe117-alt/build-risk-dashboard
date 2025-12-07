from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.entities.build_sample import BuildSample
from .base import BaseRepository


class BuildSampleRepository(BaseRepository[BuildSample]):
    def __init__(self, db: Database):
        super().__init__(db, "build_samples", BuildSample)

    def find_by_repo_and_run_id(
        self, repo_id: str, workflow_run_id: int
    ) -> Optional[BuildSample]:
        return self.find_one(
            {"repo_id": self._to_object_id(repo_id), "workflow_run_id": workflow_run_id}
        )

    def list_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 0
    ) -> tuple[List[BuildSample], int]:
        return self.paginate(
            {"repo_id": self._to_object_id(repo_id)},
            sort=[("created_at", -1)],
            skip=skip,
            limit=limit,
        )
