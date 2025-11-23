from datetime import datetime
from typing import List, Set

from bson import ObjectId

from app.models.entities.pull_request import PullRequest
from app.repositories.base import BaseRepository


class PullRequestRepository(BaseRepository[PullRequest]):
    def __init__(self, db):
        super().__init__(db, "pull_requests", PullRequest)
        # Ensure indexes
        self.collection.create_index([("repo_id", 1), ("number", 1)], unique=True)
        self.collection.create_index([("repo_id", 1), ("merged_at", -1)])

    def upsert_pull_request(self, pr_data: dict) -> PullRequest:
        """Upsert a pull request by repo_id and number."""
        repo_id = pr_data.get("repo_id")
        number = pr_data.get("number")

        if not repo_id or not number:
            raise ValueError("repo_id and number are required for upsert")

        query = {"repo_id": repo_id, "number": number}
        update = {"$set": pr_data}

        result = self.collection.find_one_and_update(
            query, update, upsert=True, return_document=True
        )
        return self._to_model(result)

    def find_merged_in_range(
        self, repo_id: str | ObjectId, start_date: datetime, end_date: datetime
    ) -> List[PullRequest]:
        """Find PRs merged within a specific time window."""
        repo_oid = self._to_object_id(repo_id)
        if not repo_oid:
            return []

        query = {
            "repo_id": repo_oid,
            "merged": True,
            "merged_at": {"$gte": start_date, "$lte": end_date},
        }
        return self.find_many(query)

    def get_mergers_in_range(
        self, repo_id: str | ObjectId, start_date: datetime, end_date: datetime
    ) -> Set[str]:
        """Get unique logins of users who merged PRs in the time window."""
        prs = self.find_merged_in_range(repo_id, start_date, end_date)
        mergers = set()
        for pr in prs:
            if pr.merged_by_login:
                mergers.add(pr.merged_by_login)
        return mergers
