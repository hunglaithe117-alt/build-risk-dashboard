"""Workflow repositories for database operations"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from pymongo.database import Database

from .base import BaseRepository


class WorkflowRunRepository(BaseRepository):
    """Repository for workflow run entities"""

    def __init__(self, db: Database):
        super().__init__(db, "workflow_runs")

    def upsert_workflow_run(
        self, run_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Insert or update a workflow run"""
        doc = payload.copy()
        doc["updated_at"] = datetime.now(timezone.utc)

        existing = self.collection.find_one({"_id": run_id})
        if existing:
            self.collection.update_one({"_id": run_id}, {"$set": doc})
        else:
            doc["_id"] = run_id
            doc["created_at"] = datetime.now(timezone.utc)
            self.collection.insert_one(doc)

        return self.collection.find_one({"_id": run_id})


class WorkflowJobRepository(BaseRepository):
    """Repository for workflow job entities"""

    def __init__(self, db: Database):
        super().__init__(db, "workflow_jobs")

    def record_workflow_jobs(self, run_id: int, jobs: List[Dict[str, Any]]) -> None:
        """Record multiple workflow jobs"""
        for job in jobs:
            job_id = job.get("id")
            if job_id is None:
                continue

            document = job.copy()
            # Parse datetime fields
            for key in ["started_at", "completed_at"]:
                value = document.get(key)
                if isinstance(value, str):
                    try:
                        document[key] = datetime.fromisoformat(
                            value.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

            document.update({"run_id": run_id, "updated_at": datetime.now(timezone.utc)})

            existing = self.collection.find_one({"_id": job_id})
            if existing:
                self.collection.update_one({"_id": job_id}, {"$set": document})
            else:
                document["_id"] = job_id
                document["created_at"] = datetime.now(timezone.utc)
                self.collection.insert_one(document)
