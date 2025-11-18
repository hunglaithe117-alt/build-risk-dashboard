"""Build repository for database operations"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from pymongo.database import Database

from .base import BaseRepository


class BuildRepository(BaseRepository):
    """Repository for build entities"""

    def __init__(self, db: Database):
        super().__init__(db, "builds")

    def find_by_repository(
        self, repository: str, skip: int = 0, limit: int = 50
    ) -> List[Dict]:
        """Find builds by repository name"""
        return self.find_many(
            {"repository": repository},
            sort=[("started_at", -1)],
            skip=skip,
            limit=limit,
        )

    def find_by_repository_and_branch(
        self, repository: str, branch: str, skip: int = 0, limit: int = 50
    ) -> List[Dict]:
        """Find builds by repository and branch"""
        return self.find_many(
            {"repository": repository, "branch": branch},
            sort=[("started_at", -1)],
            skip=skip,
            limit=limit,
        )

    def upsert_build(self, build_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a build"""
        payload = data.copy()
        payload["updated_at"] = datetime.now(timezone.utc)

        existing = self.collection.find_one({"_id": build_id})
        if existing:
            self.collection.update_one({"_id": build_id}, {"$set": payload})
        else:
            payload["_id"] = build_id
            payload["created_at"] = datetime.now(timezone.utc)
            self.collection.insert_one(payload)

        return self.collection.find_one({"_id": build_id})

    def update_features(self, build_id: int, **features: Any) -> None:
        """Update build features"""
        if not features:
            return
        update = {f"features.{key}": value for key, value in features.items()}
        update["updated_at"] = datetime.now(timezone.utc)
        self.collection.update_one({"_id": build_id}, {"$set": update})

    def append_commits(self, build_id: int, commits: List[Dict[str, Any]]) -> None:
        """Append commits to build features"""
        if not commits:
            return
        self.update_features(
            build_id,
            git_all_built_commits=commits,
            git_num_all_built_commits=len(commits),
        )

    def count_by_repository(self) -> Dict[str, int]:
        """Count builds grouped by repository"""
        pipeline = [
            {"$group": {"_id": "$repository", "count": {"$sum": 1}}},
        ]
        results = self.aggregate(pipeline)
        return {doc["_id"]: doc["count"] for doc in results if doc.get("_id")}

    def count_for_repository(self, repository: str) -> int:
        """Count builds for a specific repository"""
        return self.count({"repository": repository})
