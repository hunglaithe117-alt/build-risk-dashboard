from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.failed_scan import FailedScan, ScanStatus
from app.repositories.base import BaseRepository


class FailedScanRepository(BaseRepository[FailedScan]):
    def __init__(self, db: Database):
        super().__init__(db, "failed_scans", FailedScan)

    def get_by_job_id(self, job_id: str) -> Optional[FailedScan]:
        doc = self.collection.find_one({"job_id": ObjectId(job_id)})
        return FailedScan(**doc) if doc else None

    def list_by_repo(
        self, repo_id: str, status: Optional[str] = None, skip: int = 0, limit: int = 20
    ) -> List[FailedScan]:
        query = {"repo_id": ObjectId(repo_id)}
        if status:
            query["status"] = status

        cursor = (
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )
        return [FailedScan(**doc) for doc in cursor]

    def count_by_repo(self, repo_id: str, status: Optional[str] = None) -> int:
        query = {"repo_id": ObjectId(repo_id)}
        if status:
            query["status"] = status
        return self.collection.count_documents(query)

    def count_pending_by_repo(self, repo_id: str) -> int:
        return self.count_by_repo(repo_id, status=ScanStatus.PENDING)
