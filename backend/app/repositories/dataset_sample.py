"""
Dataset Sample Repository.

Repository for managing DatasetSample documents - extracted features
for Custom Dataset Builder jobs.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.models.entities.dataset_sample import DatasetSample
from .base import BaseRepository


class DatasetSampleRepository(BaseRepository[DatasetSample]):
    """Repository for DatasetSample collection."""
    
    def __init__(self, db: Database):
        super().__init__(db, "dataset_samples", DatasetSample)
        # Create indexes for common queries
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Create indexes for efficient querying."""
        # Index for finding samples by job
        self.collection.create_index("job_id")
        # Compound index for finding specific sample in a job
        self.collection.create_index([("job_id", 1), ("workflow_run_id", 1)], unique=True)
        # Index for finding samples by repo
        self.collection.create_index("repo_id")
    
    def find_by_job_id(
        self, 
        job_id: str, 
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> tuple[List[DatasetSample], int]:
        """Find all samples for a job, optionally filtered by status."""
        query: Dict[str, Any] = {"job_id": self._to_object_id(job_id)}
        if status:
            query["status"] = status
        
        return self.paginate(
            query,
            sort=[("build_number", -1)],
            skip=skip,
            limit=limit,
        )
    
    def find_by_job_and_run_id(
        self, 
        job_id: str, 
        workflow_run_id: int
    ) -> Optional[DatasetSample]:
        """Find a sample by job ID and workflow run ID."""
        return self.find_one({
            "job_id": self._to_object_id(job_id),
            "workflow_run_id": workflow_run_id,
        })
    
    def get_completed_samples(
        self, 
        job_id: str,
        limit: Optional[int] = None,
    ) -> List[DatasetSample]:
        """
        Get all completed samples for a job.
        
        Sorted by build_number ASC (oldest -> newest) to maintain
        chronological order in the exported dataset.
        """
        query = {
            "job_id": self._to_object_id(job_id),
            "status": "completed",
        }
        # Sort ascending by build_number (oldest first)
        cursor = self.collection.find(query).sort("build_number", 1)
        
        if limit:
            cursor = cursor.limit(limit)
        
        return [DatasetSample(**doc) for doc in cursor]
    
    def update_status(
        self,
        sample_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update sample status."""
        update: Dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if error_message:
            update["error_message"] = error_message
        
        result = self.collection.update_one(
            {"_id": self._to_object_id(sample_id)},
            {"$set": update},
        )
        return result.modified_count > 0
    
    def save_features(
        self,
        sample_id: str,
        features: Dict[str, Any],
    ) -> bool:
        """Save extracted features for a sample."""
        result = self.collection.update_one(
            {"_id": self._to_object_id(sample_id)},
            {"$set": {
                "features": features,
                "status": "completed",
                "extracted_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
        )
        return result.modified_count > 0
    
    def get_job_stats(self, job_id: str) -> Dict[str, int]:
        """Get statistics for a job's samples."""
        pipeline = [
            {"$match": {"job_id": self._to_object_id(job_id)}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }},
        ]
        
        results = list(self.collection.aggregate(pipeline))
        stats = {
            "total": 0,
            "pending": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
        }
        
        for r in results:
            status = r["_id"]
            count = r["count"]
            stats["total"] += count
            if status in stats:
                stats[status] = count
        
        return stats
    
    def delete_by_job_id(self, job_id: str) -> int:
        """Delete all samples for a job."""
        result = self.collection.delete_many({
            "job_id": self._to_object_id(job_id)
        })
        return result.deleted_count
    
    def bulk_insert(self, samples: List[Dict[str, Any]]) -> List[ObjectId]:
        """Insert multiple samples at once."""
        if not samples:
            return []
        
        now = datetime.now(timezone.utc)
        for sample in samples:
            sample.setdefault("created_at", now)
            sample.setdefault("updated_at", now)
            sample.setdefault("status", "pending")
            sample.setdefault("features", {})
        
        result = self.collection.insert_many(samples)
        return result.inserted_ids
