"""Helpers for recording queue health metrics."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from pymongo.database import Database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_schedule_heartbeat(db: Database, scheduled_repositories: int) -> Dict[str, object]:
    pending_imports = db.github_import_jobs.count_documents({"status": {"$in": ["pending", "queued"]}})
    running_imports = db.github_import_jobs.count_documents({"status": "running"})
    builds_waiting = db.builds.count_documents({"features.tr_log_tests_fail_rate": {"$exists": False}})
    completed_builds = db.builds.count_documents({"features.tr_log_tests_fail_rate": {"$exists": True}})

    document = {
        "timestamp": _utcnow(),
        "repositories_scheduled": scheduled_repositories,
        "pending_import_jobs": pending_imports,
        "running_import_jobs": running_imports,
        "builds_waiting_enrichment": builds_waiting,
        "completed_builds": completed_builds,
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
        "pending_import_jobs": latest.get("pending_import_jobs", 0),
        "running_import_jobs": latest.get("running_import_jobs", 0),
        "builds_waiting_enrichment": latest.get("builds_waiting_enrichment", 0),
        "completed_builds": latest.get("completed_builds", 0),
    }
