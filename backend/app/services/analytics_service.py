"""Analytics service using repository metadata only."""

from typing import Dict

from pymongo.database import Database


def compute_dashboard_summary(db: Database) -> Dict[str, object]:
    """Return a lightweight dashboard summary derived from repository data."""
    repositories = list(db.repositories.find())
    total_builds = sum(int(repo.get("total_builds_imported", 0) or 0) for repo in repositories)

    repo_distribution = [
        {
            "repository": repo.get("full_name") or "unknown",
            "builds": int(repo.get("total_builds_imported", 0) or 0),
        }
        for repo in repositories
    ]

    return {
        "metrics": {
            "total_builds": total_builds,
            "success_rate": 0.0,
            "average_duration_minutes": 0.0,
        },
        "trends": [],
        "repo_distribution": repo_distribution,
    }
