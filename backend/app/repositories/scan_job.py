from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.scan_job import ScanJob
from app.repositories.base import BaseRepository


class ScanJobRepository(BaseRepository[ScanJob]):
    def __init__(self, db: Database):
        super().__init__(db, "scan_jobs", ScanJob)

    def get_by_build_id(self, build_id: str) -> Optional[ScanJob]:
        doc = self.collection.find_one({"build_id": ObjectId(build_id)})
        return ScanJob(**doc) if doc else None

    def list_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 20
    ) -> List[ScanJob]:
        cursor = (
            self.collection.find({"repo_id": ObjectId(repo_id)})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [ScanJob(**doc) for doc in cursor]

    def count_by_repo(self, repo_id: str) -> int:
        return self.collection.count_documents({"repo_id": ObjectId(repo_id)})
