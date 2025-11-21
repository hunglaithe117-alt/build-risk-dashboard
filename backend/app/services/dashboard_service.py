from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from pymongo.database import Database

from app.dtos import DashboardSummaryResponse, DashboardMetrics, RepoDistributionEntry


class DashboardService:
    def __init__(self, db: Database):
        self.db = db
        self.build_collection = db["build_samples"]
        self.repo_collection = db["repositories"]

    def get_summary(self) -> DashboardSummaryResponse:
        # 1. Calculate total builds (last 14 days)
        two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)

        total_builds = self.build_collection.count_documents({})

        # 2. Success rate
        successful_builds = self.build_collection.count_documents(
            {"tr_status": "passed"}
        )
        success_rate = (
            (successful_builds / total_builds * 100) if total_builds > 0 else 0.0
        )

        # 3. Average duration
        pipeline = [
            {"$match": {"tr_duration": {"$ne": None}}},
            {"$group": {"_id": None, "avg_duration": {"$avg": "$tr_duration"}}},
        ]
        avg_duration_result = list(self.build_collection.aggregate(pipeline))
        avg_duration_seconds = (
            avg_duration_result[0]["avg_duration"] if avg_duration_result else 0
        )
        avg_duration_minutes = avg_duration_seconds / 60 if avg_duration_seconds else 0

        # 4. Repo distribution
        repos = list(self.repo_collection.find({"import_status": "imported"}))
        repo_distribution = []
        for repo in repos:
            repo_id = repo["_id"]
            build_count = self.build_collection.count_documents({"repo_id": repo_id})
            repo_distribution.append(
                RepoDistributionEntry(repository=repo["full_name"], builds=build_count)
            )

        # Sort by builds desc
        repo_distribution.sort(key=lambda x: x.builds, reverse=True)

        return DashboardSummaryResponse(
            metrics=DashboardMetrics(
                total_builds=total_builds,
                success_rate=success_rate,
                average_duration_minutes=avg_duration_minutes,
            ),
            trends=[],  # Can be implemented later
            repo_distribution=repo_distribution,
        )
