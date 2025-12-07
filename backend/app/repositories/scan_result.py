from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.scan_result import ScanResult
from app.repositories.base import BaseRepository


class ScanResultRepository(BaseRepository[ScanResult]):
    def __init__(self, db: Database):
        super().__init__(db, "scan_results", ScanResult)

    def get_by_job_id(self, job_id: str) -> Optional[ScanResult]:
        doc = self.collection.find_one({"job_id": ObjectId(job_id)})
        return ScanResult(**doc) if doc else None

    def list_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 20
    ) -> List[ScanResult]:
        cursor = (
            self.collection.find({"repo_id": ObjectId(repo_id)})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [ScanResult(**doc) for doc in cursor]

    def count_by_repo(self, repo_id: str) -> int:
        return self.collection.count_documents({"repo_id": ObjectId(repo_id)})

    def upsert_by_job(self, job_id: str, data: dict) -> ScanResult:
        """Create or update scan result by job_id."""
        existing = self.collection.find_one({"job_id": ObjectId(job_id)})
        if existing:
            self.collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {**data, "updated_at": data.get("updated_at")}},
            )
            updated_doc = self.collection.find_one({"_id": existing["_id"]})
            return ScanResult(**updated_doc)
        else:
            result = self.collection.insert_one(data)
            new_doc = self.collection.find_one({"_id": result.inserted_id})
            return ScanResult(**new_doc)
