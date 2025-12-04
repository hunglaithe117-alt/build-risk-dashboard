"""
Dataset Job Repository.

CRUD operations for dataset jobs.
"""

from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.models.entities.dataset_job import DatasetJob, DatasetJobStatus
from app.repositories.base import BaseRepository


class DatasetJobRepository(BaseRepository[DatasetJob]):
    """Repository for dataset jobs."""
    
    def __init__(self, db: Database):
        super().__init__(db, "dataset_jobs", DatasetJob)
        # Create indexes
        self.collection.create_index("user_id")
        self.collection.create_index("status")
        self.collection.create_index("created_at")
        self.collection.create_index([("user_id", 1), ("created_at", -1)])
    
    def _doc_to_model(self, doc: dict) -> Optional[DatasetJob]:
        """Convert document to model, extracting created_at from _id if missing."""
        if not doc:
            return None
        if "created_at" not in doc and "_id" in doc:
            # Extract timestamp from ObjectId
            doc["created_at"] = doc["_id"].generation_time
        return DatasetJob(**doc)
    
    def find_by_id(self, entity_id: str | ObjectId) -> Optional[DatasetJob]:
        """Find a job by its ID, with created_at fallback."""
        from bson.errors import InvalidId
        try:
            identifier = ObjectId(entity_id) if isinstance(entity_id, str) else entity_id
        except InvalidId:
            return None
        doc = self.collection.find_one({"_id": identifier})
        return self._doc_to_model(doc)
    
    def find_by_user(
        self, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 20,
        status: Optional[DatasetJobStatus] = None,
    ) -> tuple[List[DatasetJob], int]:
        """Find jobs by user with pagination."""
        query: dict = {"user_id": ObjectId(user_id)}
        if status:
            query["status"] = status.value if isinstance(status, DatasetJobStatus) else status
        
        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        items = [self._doc_to_model(doc) for doc in cursor]
        
        return items, total
    
    def find_pending(self, limit: int = 10) -> List[DatasetJob]:
        """Find pending jobs to process."""
        cursor = self.collection.find(
            {"status": DatasetJobStatus.PENDING.value}
        ).sort("created_at", 1).limit(limit)
        return [self._doc_to_model(doc) for doc in cursor]
    
    def update_status(
        self, 
        job_id: str, 
        status: DatasetJobStatus,
        error_message: Optional[str] = None,
        **extra_fields
    ) -> Optional[DatasetJob]:
        """Update job status."""
        updates = {
            "status": status.value if isinstance(status, DatasetJobStatus) else status,
            "updated_at": datetime.now(timezone.utc),
            **extra_fields,
        }
        if error_message:
            updates["error_message"] = error_message
        if status == DatasetJobStatus.PROCESSING and "started_at" not in extra_fields:
            updates["started_at"] = datetime.now(timezone.utc)
        if status in [DatasetJobStatus.COMPLETED, DatasetJobStatus.FAILED]:
            updates["completed_at"] = datetime.now(timezone.utc)
        
        return self.update_one(job_id, updates)
    
    def update_progress(
        self, 
        job_id: str, 
        processed_builds: int,
        failed_builds: int = 0,
        current_phase: str = "",
    ) -> Optional[DatasetJob]:
        """Update job progress."""
        return self.update_one(job_id, {
            "processed_builds": processed_builds,
            "failed_builds": failed_builds,
            "current_phase": current_phase,
            "updated_at": datetime.now(timezone.utc),
        })
    
    def set_output(
        self,
        job_id: str,
        file_path: str,
        file_size: int,
        row_count: int,
    ) -> Optional[DatasetJob]:
        """Set output file info."""
        return self.update_one(job_id, {
            "output_file_path": file_path,
            "output_file_size": file_size,
            "output_row_count": row_count,
            "updated_at": datetime.now(timezone.utc),
        })
    
    def increment_download_count(self, job_id: str) -> Optional[DatasetJob]:
        """Increment download counter."""
        self.collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$inc": {"download_count": 1}}
        )
        return self.find_by_id(ObjectId(job_id))
