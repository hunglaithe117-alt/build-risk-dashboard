"""Helpers describing the preprocessing / normalization pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from pymongo.database import Database


def _stage(
    key: str,
    label: str,
    status: str,
    percent: int,
    started_at: datetime,
    duration_minutes: int,
    items: int,
    notes: str = "",
    issues: List[str] | None = None,
) -> Dict[str, object]:
    completed_at = (
        started_at + timedelta(minutes=duration_minutes) if status in {"completed", "running"} else None
    )
    return {
        "key": key,
        "label": label,
        "status": status,
        "percent_complete": percent,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration_minutes * 60,
        "items_processed": items,
        "notes": notes or None,
        "issues": issues or [],
    }


def compute_pipeline_status(db: Database) -> Dict[str, object]:
    builds = list(db.builds.find())
    total_builds = len(builds)
    repositories = {build.get("repository", "unknown") for build in builds}

    now = datetime.now(timezone.utc)
    last_run = now - timedelta(minutes=12)
    next_run = now + timedelta(minutes=18)

    ingested = total_builds
    enriched = max(0, int(total_builds * 0.92))
    normalized = max(0, int(total_builds * 0.78))
    feature_ready = max(0, int(total_builds * 0.64))
    scored = max(0, int(total_builds * 0.5))

    stages = [
        _stage(
            key="ingestion",
            label="Collect workflow runs",
            status="completed",
            percent=100,
            started_at=last_run - timedelta(minutes=25),
            duration_minutes=6,
            items=ingested,
            notes="GitHub Actions + CircleCI collectors completed.",
        ),
        _stage(
            key="enrichment",
            label="Enrich commits/logs data",
            status="completed",
            percent=96,
            started_at=last_run - timedelta(minutes=19),
            duration_minutes=5,
            items=enriched,
            notes="Linked test artifacts and internal metrics.",
        ),
        _stage(
            key="normalization",
            label="Normalization & feature engineering",
            status="running",
            percent=78,
            started_at=last_run - timedelta(minutes=12),
            duration_minutes=8,
            items=normalized,
            notes="Normalizing inputs for the Bayesian CNN model.",
            issues=[
                "Missing coverage report from buildguard/ui-dashboard",
                "No new metrics found for branch feature/github-sync",
            ],
        ),
        _stage(
            key="feature_store",
            label="Sync Feature Store",
            status="running",
            percent=64,
            started_at=last_run - timedelta(minutes=6),
            duration_minutes=6,
            items=feature_ready,
            notes="Push feature vectors to Redis/Parquet.",
        ),
        _stage(
            key="analysis",
                label="Scoring & analysis",
                status="pending",
                percent=45,
                started_at=last_run - timedelta(minutes=3),
                duration_minutes=5,
                items=scored,
                notes="Model scoring currently disabled — analysis placeholder.",
        ),
    ]

    return {
        "last_run": last_run,
        "next_run": next_run,
        "normalized_features": normalized * 128,
        "pending_repositories": max(0, 6 - len(repositories)),
        "stages": stages,
    }
