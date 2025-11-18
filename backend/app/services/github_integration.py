"""GitHub integration status helpers backed by MongoDB."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from pymongo.database import Database

from app.config import settings
from app.services.pipeline_store import PipelineStore
from app.tasks.repositories import enqueue_repo_import


def _aggregate_repo_stats(builds: List[dict]) -> List[dict]:
    repo_map: Dict[str, Dict[str, object]] = {}
    for build in builds:
        repository = build.get("repository", "unknown")
        repo_stats = repo_map.setdefault(
            repository,
            {
                "name": repository,
                "buildCount": 0,
                "status": "healthy",
                "lastSync": build.get("updated_at") or build.get("created_at"),
            },
        )
        repo_stats["buildCount"] += 1

        candidate_date = build.get("updated_at") or build.get("created_at")
        last_sync = repo_stats.get("lastSync")
        if candidate_date and (last_sync is None or candidate_date > last_sync):
            repo_stats["lastSync"] = candidate_date

    results = []
    for stats in repo_map.values():
        last_sync = stats.get("lastSync")
        if isinstance(last_sync, str):
            stats["lastSync"] = last_sync
        elif hasattr(last_sync, "isoformat"):
            stats["lastSync"] = last_sync.isoformat()
        else:
            stats["lastSync"] = None

        results.append(stats)
    return results


def get_github_status(db: Database) -> Dict[str, object]:
    connection = db.github_connection.find_one({})
    scopes = settings.GITHUB_SCOPES or ["read:user", "repo", "read:org", "workflow"]

    if not connection:
        return {
            "connected": False,
            "organization": None,
            "connectedAt": None,
            "scopes": scopes,
            "repositories": [],
            "lastSyncStatus": "warning",
            "lastSyncMessage": "GitHub OAuth not authorized.",
            "accountLogin": None,
            "accountName": None,
            "accountAvatarUrl": None,
        }

    builds = list(db.builds.find())
    repositories = _aggregate_repo_stats(builds)

    status = connection.get("last_sync_status", "warning")
    message = connection.get(
        "last_sync_message", "Collector has not run since authorization."
    )

    connected_at = connection.get("connected_at")
    if hasattr(connected_at, "isoformat"):
        connected_at = connected_at.isoformat()

    return {
        "connected": True,
        "organization": connection.get("organization")
        or connection.get("account_login"),
        "connectedAt": connected_at,
        "scopes": scopes,
        "repositories": repositories,
        "lastSyncStatus": status,
        "lastSyncMessage": message,
        "accountLogin": connection.get("account_login"),
        "accountName": connection.get("account_name"),
        "accountAvatarUrl": connection.get("account_avatar_url"),
    }


def list_import_jobs(db: Database) -> List[Dict[str, object]]:
    store = PipelineStore(db)
    return store.list_import_jobs()


def create_import_job(
    db: Database,
    repository: str,
    branch: str,
    initiated_by: str = "admin",
    user_id: int | None = None,
    installation_id: str | None = None,
) -> Dict[str, object]:
    store = PipelineStore(db)
    owner_id = user_id or settings.DEFAULT_REPO_OWNER_ID
    job = store.create_import_job(
        repository,
        branch,
        initiated_by,
        user_id=owner_id,
        installation_id=installation_id,
    )
    job_id = job.get("id")
    start_time = datetime.now(timezone.utc)

    store.update_import_job(
        job_id,
        status="queued",
        progress=1,
        started_at=start_time,
        notes="Collecting repository metadata",
    )
    enqueue_repo_import.delay(repository, branch, job_id, owner_id, installation_id)
    return store.update_import_job(
        job_id,
        status="waiting_webhook",
        notes="Metadata collected. Configure the GitHub webhook to receive workflow events.",
    )
