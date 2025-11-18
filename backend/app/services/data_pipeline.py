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
            label="Thu thập workflow runs",
            status="completed",
            percent=100,
            started_at=last_run - timedelta(minutes=25),
            duration_minutes=6,
            items=ingested,
            notes="GitHub Actions + CircleCI collectors hoàn tất.",
        ),
        _stage(
            key="enrichment",
            label="Làm giàu dữ liệu commits/logs",
            status="completed",
            percent=96,
            started_at=last_run - timedelta(minutes=19),
            duration_minutes=5,
            items=enriched,
            notes="Đã ghép test artifacts và metrics nội bộ.",
        ),
        _stage(
            key="normalization",
            label="Chuẩn hóa & feature engineering",
            status="running",
            percent=78,
            started_at=last_run - timedelta(minutes=12),
            duration_minutes=8,
            items=normalized,
            notes="Chuẩn hóa dữ liệu đầu vào mô hình Bayesian CNN.",
            issues=[
                "Thiếu coverage report từ buildguard/ui-dashboard",
                "Chưa tìm thấy metrics mới cho branch feature/github-sync",
            ],
        ),
        _stage(
            key="feature_store",
            label="Đồng bộ Feature Store",
            status="running",
            percent=64,
            started_at=last_run - timedelta(minutes=6),
            duration_minutes=6,
            items=feature_ready,
            notes="Đẩy vector đặc trưng sang Redis/Parquet.",
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
