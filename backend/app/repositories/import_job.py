"""Import job repository for database operations"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pymongo.database import Database

from .base import BaseRepository


class ImportJobRepository(BaseRepository):
    """Repository for import job entities"""

    def __init__(self, db: Database):
        super().__init__(db, "github_import_jobs")

    def find_by_repository(self, repository: str, limit: int = 20) -> List[Dict]:
        """Find import jobs for a repository"""
        return self.find_many(
            {"repository": repository}, sort=[("created_at", -1)], limit=limit
        )

    def list_all(self) -> List[Dict]:
        """List all import jobs"""
        return self.find_many({}, sort=[("created_at", -1)])

    def create_import_job(
        self,
        repository: str,
        branch: str,
        initiated_by: str,
        user_id: Optional[str] = None,
        installation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new import job"""
        now = datetime.now(timezone.utc)
        doc = {
            "_id": uuid4().hex,
            "repository": repository,
            "branch": branch,
            "status": "pending",
            "progress": 0,
            "builds_imported": 0,
            "commits_analyzed": 0,
            "tests_collected": 0,
            "initiated_by": initiated_by,
            "user_id": user_id,
            "installation_id": installation_id,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "last_error": None,
            "notes": None,
        }
        return self.insert_one(doc)

    def update_job(self, job_id: str, **updates: Any) -> Optional[Dict[str, Any]]:
        """Update an import job"""
        updates.setdefault("updated_at", datetime.now(timezone.utc))
        return self.update_one(job_id, updates)
