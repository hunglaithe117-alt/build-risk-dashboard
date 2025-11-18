"""Analytics service using repository pattern"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from pymongo.database import Database

from app.repositories.build import BuildRepository


def _same_day(a: datetime, b: datetime) -> bool:
    return a.date() == b.date()


def _ensure_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def compute_dashboard_summary(db: Database) -> Dict[str, object]:
    """Compute dashboard analytics summary"""
    build_repo = BuildRepository(db)
    builds = build_repo.find_many({})
    total_builds = len(builds)

    if total_builds == 0:
        return {
            "metrics": {
                "total_builds": 0,
                "success_rate": 0.0,
                "average_duration_minutes": 0.0,
            },
            "trends": [],
            "repo_distribution": [],
        }

    total_duration = 0
    duration_count = 0
    completed_builds = 0
    successful_builds = 0

    for build in builds:
        duration_seconds = build.get("duration_seconds")
        if duration_seconds:
            total_duration += duration_seconds
            duration_count += 1

        if build.get("status") == "completed":
            completed_builds += 1
            if build.get("conclusion") == "success":
                successful_builds += 1

    average_duration_minutes = (
        (total_duration / duration_count / 60) if duration_count else 0.0
    )
    success_rate = (
        (successful_builds / completed_builds) * 100 if completed_builds else 0.0
    )

    today = datetime.now(timezone.utc)
    trend_days = [today - timedelta(days=offset) for offset in range(9, -1, -1)]

    trends = []
    for day in trend_days:
        day_builds = []
        for build in builds:
            completed_at = _ensure_datetime(build.get("completed_at"))
            if completed_at and _same_day(completed_at, day):
                day_builds.append(build)

        trend = {
            "date": day.strftime("%d/%m"),
            "builds": len(day_builds),
            "failures": sum(
                1 for build in day_builds if build.get("conclusion") == "failure"
            ),
        }
        trends.append(trend)

    repo_map: Dict[str, Dict[str, int]] = defaultdict(lambda: {"builds": 0})
    for build in builds:
        repo = build.get("repository", "unknown")
        stats = repo_map[repo]
        stats["builds"] += 1

    repo_distribution = [
        {"repository": repo, "builds": stats["builds"]}
        for repo, stats in repo_map.items()
    ]

    return {
        "metrics": {
            "total_builds": total_builds,
            "success_rate": round(success_rate, 1),
            "average_duration_minutes": round(average_duration_minutes, 1),
        },
        "trends": trends,
        "repo_distribution": repo_distribution,
    }
