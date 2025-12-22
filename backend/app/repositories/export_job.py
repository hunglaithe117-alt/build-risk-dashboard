"""
Export Job Repository - Database operations for export jobs.
"""

from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.export_job import ExportJob


class ExportJobRepository:
    """Repository for ExportJob entities."""

    def __init__(self, db: Database):
        self.db = db
        self.collection = db.export_jobs

    def create(self, job: ExportJob) -> ExportJob:
        """Create a new export job."""
        doc = job.model_dump(by_alias=True, exclude={"id"})
        doc["created_at"] = datetime.now(timezone.utc)
        doc["updated_at"] = datetime.now(timezone.utc)
        result = self.collection.insert_one(doc)
        job.id = result.inserted_id
        return job

    def find_by_id(self, job_id: str) -> Optional[ExportJob]:
        """Find export job by ID."""
        doc = self.collection.find_one({"_id": ObjectId(job_id)})
        return ExportJob(**doc) if doc else None

    def update_status(self, job_id: str, status: str, **kwargs) -> None:
        """Update export job status and optional fields."""
        updates = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
            **kwargs,
        }
        self.collection.update_one({"_id": ObjectId(job_id)}, {"$set": updates})

    def update_progress(self, job_id: str, processed_rows: int) -> None:
        """Update processed row count."""
        self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$set": {
                    "processed_rows": processed_rows,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    def list_by_repo(self, repo_id: str, limit: int = 10) -> List[ExportJob]:
        """List export jobs for a repository, newest first."""
        cursor = (
            self.collection.find({"repo_id": ObjectId(repo_id)}).sort("created_at", -1).limit(limit)
        )
        return [ExportJob(**doc) for doc in cursor]

    def list_by_user(self, user_id: str, limit: int = 20) -> List[ExportJob]:
        """List export jobs for a user, newest first."""
        cursor = (
            self.collection.find({"user_id": ObjectId(user_id)}).sort("created_at", -1).limit(limit)
        )
        return [ExportJob(**doc) for doc in cursor]

    def delete_old_jobs(self, days: int = 7) -> int:
        """Delete export jobs older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.collection.delete_many({"created_at": {"$lt": cutoff}})
        return result.deleted_count


from datetime import timedelta
