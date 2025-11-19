"""Helpers for recording queue health metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from pymongo.database import Database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_schedule_heartbeat(db: Database, scheduled_repositories: int) -> Dict[str, object]:
    document = {
        "timestamp": _utcnow(),
        "repositories_scheduled": scheduled_repositories,
    }
    db.queue_metrics.insert_one(document)
    return document


def get_queue_health(db: Database) -> Dict[str, object]:
    latest = db.queue_metrics.find_one(sort=[("timestamp", -1)])
    if not latest:
        latest = record_schedule_heartbeat(db, 0)

    return {
        "last_heartbeat": latest.get("timestamp"),
        "repositories_scheduled": latest.get("repositories_scheduled", 0),
    }
