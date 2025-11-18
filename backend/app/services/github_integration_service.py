"""GitHub integration service using repository pattern"""

from datetime import datetime, timezone
from typing import Dict, List

from pymongo.database import Database

from app.repositories.import_job import ImportJobRepository
from app.tasks.repositories import enqueue_repo_import


def list_import_jobs(db: Database) -> List[Dict[str, object]]:
    """List all import jobs"""
    import_job_repo = ImportJobRepository(db)
    jobs = import_job_repo.list_all()
    # Serialize for JSON response
    return [_serialize_job(job) for job in jobs]


def create_import_job(
    db: Database,
    repository: str,
    branch: str,
    initiated_by: str = "admin",
    user_id: str | None = None,
    installation_id: str | None = None,
) -> Dict[str, object]:
    """Create a new import job and queue it"""
    import_job_repo = ImportJobRepository(db)
    
    job = import_job_repo.create_import_job(
        repository=repository,
        branch=branch,
        initiated_by=initiated_by,
        user_id=user_id,
        installation_id=installation_id,
    )
    
    job_id = str(job.get("_id"))
    start_time = datetime.now(timezone.utc)

    import_job_repo.update_job(
        job_id,
        status="queued",
        progress=1,
        started_at=start_time,
        notes="Collecting repository metadata",
    )
    
    enqueue_repo_import.delay(repository, branch, job_id, user_id, installation_id)
    
    updated_job = import_job_repo.update_job(
        job_id,
        status="waiting_webhook",
        notes="Metadata collected. Configure the GitHub webhook to receive workflow events.",
    )
    
    return _serialize_job(updated_job)


def _serialize_job(job: Dict) -> Dict:
    """Serialize job for JSON response"""
    if not job:
        return {}
    
    payload = job.copy()
    identifier = payload.pop("_id", None)
    if identifier is not None:
        payload["id"] = str(identifier)
    
    # Convert ObjectId fields to strings
    if payload.get("user_id") is not None:
        from bson import ObjectId
        if isinstance(payload["user_id"], ObjectId):
            payload["user_id"] = str(payload["user_id"])
    
    # Convert datetime to ISO format
    for key, value in payload.items():
        if isinstance(value, datetime):
            payload[key] = value.isoformat()
    
    return payload
