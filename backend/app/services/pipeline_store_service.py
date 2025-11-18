"""Pipeline store service using repository pattern - compatibility layer"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.repositories.build import BuildRepository
from app.repositories.import_job import ImportJobRepository
from app.repositories.repository import RepositoryRepository
from app.repositories.workflow import WorkflowJobRepository, WorkflowRunRepository


class PipelineStore:
    """
    Facade for persisting pipeline entities.
    This is a compatibility layer that uses repositories internally.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.repo_repo = RepositoryRepository(db)
        self.build_repo = BuildRepository(db)
        self.import_job_repo = ImportJobRepository(db)
        self.workflow_run_repo = WorkflowRunRepository(db)
        self.workflow_job_repo = WorkflowJobRepository(db)

    def upsert_repository(
        self,
        *,
        user_id: Optional[str],
        provider: str,
        full_name: str,
        default_branch: str,
        is_private: bool,
        main_lang: Optional[str],
        github_repo_id: Optional[int],
        metadata: Dict[str, Any],
        last_scanned_at: Optional[datetime] = None,
        installation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upsert a repository"""
        return self.repo_repo.upsert_repository(
            user_id=user_id,
            provider=provider,
            full_name=full_name,
            default_branch=default_branch,
            is_private=is_private,
            main_lang=main_lang,
            github_repo_id=github_repo_id,
            metadata=metadata,
            last_scanned_at=last_scanned_at,
            installation_id=installation_id,
        )

    def update_repository(
        self, repo_id: str | ObjectId, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a repository"""
        return self.repo_repo.update_repository(str(repo_id), updates)

    def list_repositories(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List repositories"""
        return self.repo_repo.list_by_user(user_id)

    def count_builds_by_repository(self) -> Dict[str, int]:
        """Count builds grouped by repository"""
        return self.build_repo.count_by_repository()

    def count_builds_for_repo(self, repository: str) -> int:
        """Count builds for a repository"""
        return self.build_repo.count_for_repository(repository)

    def list_repo_jobs(self, repository: str, limit: int = 20) -> List[Dict[str, Any]]:
        """List import jobs for a repository"""
        jobs = self.import_job_repo.find_by_repository(repository, limit)
        return [_serialize_job(job) for job in jobs]

    def get_repository(self, repo_id: str | ObjectId) -> Optional[Dict[str, Any]]:
        """Get a repository by ID"""
        return self.repo_repo.find_by_id(str(repo_id))

    def upsert_workflow_run(
        self, run_id: int, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Upsert a workflow run"""
        return self.workflow_run_repo.upsert_workflow_run(run_id, payload)

    def record_workflow_jobs(self, run_id: int, jobs: List[Dict[str, Any]]) -> None:
        """Record workflow jobs"""
        self.workflow_job_repo.record_workflow_jobs(run_id, jobs)

    def upsert_build(self, build_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a build"""
        return self.build_repo.upsert_build(build_id, data)

    def append_build_commits(
        self, build_id: int, commits: List[Dict[str, Any]]
    ) -> None:
        """Append commits to build"""
        self.build_repo.append_commits(build_id, commits)

    def record_build_feature_block(
        self, build_id: int, block: str, data: Dict[str, Any]
    ) -> None:
        """Record build feature block"""
        prefixed = {f"{block}.{key}": value for key, value in data.items()}
        self.build_repo.update_features(build_id, **prefixed)

    def update_build_features(self, build_id: int, **features: Any) -> None:
        """Update build features"""
        self.build_repo.update_features(build_id, **features)

    def create_import_job(
        self,
        repository: str,
        branch: str,
        initiated_by: str,
        user_id: Optional[str] = None,
        installation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create an import job"""
        job = self.import_job_repo.create_import_job(
            repository=repository,
            branch=branch,
            initiated_by=initiated_by,
            user_id=user_id,
            installation_id=installation_id,
        )
        return _serialize_job(job)

    def update_import_job(self, job_id: str, **updates: Any) -> Dict[str, Any]:
        """Update an import job"""
        job = self.import_job_repo.update_job(job_id, **updates)
        return _serialize_job(job) if job else {}

    def list_import_jobs(self) -> List[Dict[str, Any]]:
        """List all import jobs"""
        jobs = self.import_job_repo.list_all()
        return [_serialize_job(job) for job in jobs]

    def get_workflow_cursor(
        self, repository: str, branch: str
    ) -> Optional[Dict[str, Any]]:
        """Get workflow cursor"""
        return self.db.workflow_cursors.find_one(
            {"repository": repository, "branch": branch}
        )

    def update_workflow_cursor(
        self, repository: str, branch: str, run_id: int, started_at: datetime
    ) -> None:
        """Update workflow cursor"""
        from datetime import timezone

        now = datetime.now(timezone.utc)
        document = {
            "repository": repository,
            "branch": branch,
            "last_run_id": run_id,
            "last_run_started_at": started_at,
            "updated_at": now,
        }
        self.db.workflow_cursors.update_one(
            {"repository": repository, "branch": branch},
            {
                "$set": document,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )


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
