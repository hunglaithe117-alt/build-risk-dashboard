"""
EnrichmentJob Repository - CRUD operations for enrichment jobs.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.enrichment_job import EnrichmentJob

logger = logging.getLogger(__name__)


class EnrichmentJobRepository:
    """Repository for EnrichmentJob entities."""

    COLLECTION_NAME = "enrichment_jobs"

    def __init__(self, db: Database):
        self.db = db
        self.collection = db[self.COLLECTION_NAME]

    def create(self, job: EnrichmentJob) -> EnrichmentJob:
        """Create a new enrichment job."""
        data = job.model_dump(exclude={"id"})
        result = self.collection.insert_one(data)
        job.id = result.inserted_id
        return job

    def find_by_id(self, job_id: str) -> Optional[EnrichmentJob]:
        """Find job by ID."""
        try:
            doc = self.collection.find_one({"_id": ObjectId(job_id)})
            if doc:
                return EnrichmentJob(**doc)
            return None
        except Exception:
            return None

    def find_by_dataset(self, dataset_id: str) -> List[EnrichmentJob]:
        """Find all jobs for a dataset."""
        docs = self.collection.find(
            {"dataset_id": dataset_id}
        ).sort("created_at", -1)
        return [EnrichmentJob(**doc) for doc in docs]

    def find_active_by_dataset(self, dataset_id: str) -> Optional[EnrichmentJob]:
        """Find running or pending job for a dataset."""
        doc = self.collection.find_one({
            "dataset_id": dataset_id,
            "status": {"$in": ["pending", "running"]},
        })
        if doc:
            return EnrichmentJob(**doc)
        return None

    def find_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[EnrichmentJob]:
        """Find jobs for a user."""
        docs = self.collection.find(
            {"user_id": user_id}
        ).sort("created_at", -1).skip(skip).limit(limit)
        return [EnrichmentJob(**doc) for doc in docs]

    def update_one(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job by ID."""
        updates["updated_at"] = datetime.now(timezone.utc)
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": updates}
        )
        return result.modified_count > 0

    def update_progress(
        self,
        job_id: str,
        processed_rows: int,
        enriched_rows: int,
        failed_rows: int,
        row_error: Optional[Dict] = None,
    ) -> bool:
        """Update job progress atomically."""
        updates: Dict[str, Any] = {
            "processed_rows": processed_rows,
            "enriched_rows": enriched_rows,
            "failed_rows": failed_rows,
            "updated_at": datetime.now(timezone.utc),
        }
        
        update_ops: Dict[str, Any] = {"$set": updates}
        
        if row_error:
            update_ops["$push"] = {"row_errors": row_error}
        
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            update_ops
        )
        return result.modified_count > 0

    def mark_started(self, job_id: str, celery_task_id: Optional[str] = None) -> bool:
        """Mark job as started."""
        updates = {
            "status": "running",
            "started_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        if celery_task_id:
            updates["celery_task_id"] = celery_task_id
        
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": updates}
        )
        return result.modified_count > 0

    def mark_completed(self, job_id: str, output_file: Optional[str] = None) -> bool:
        """Mark job as completed."""
        updates: Dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        if output_file:
            updates["output_file"] = output_file
        
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": updates}
        )
        return result.modified_count > 0

    def mark_failed(self, job_id: str, error: str) -> bool:
        """Mark job as failed."""
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {
                "status": "failed",
                "error": error,
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }}
        )
        return result.modified_count > 0

    def mark_cancelled(self, job_id: str) -> bool:
        """Mark job as cancelled."""
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {
                "status": "cancelled",
                "completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }}
        )
        return result.modified_count > 0

    def add_auto_imported_repo(self, job_id: str, repo_name: str) -> bool:
        """Add a repo to the auto-imported list."""
        result = self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$push": {"repos_auto_imported": repo_name},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            }
        )
        return result.modified_count > 0

    def delete(self, job_id: str) -> bool:
        """Delete a job."""
        result = self.collection.delete_one({"_id": ObjectId(job_id)})
        return result.deleted_count > 0

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """Delete completed jobs older than N days."""
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.collection.delete_many({
            "status": {"$in": ["completed", "failed", "cancelled"]},
            "completed_at": {"$lt": cutoff},
        })
        return result.deleted_count
