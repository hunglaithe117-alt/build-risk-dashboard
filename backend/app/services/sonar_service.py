import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.scan_job import ScanJob, ScanJobStatus
from app.entities.failed_scan import FailedScan, ScanStatus
from app.repositories.scan_job import ScanJobRepository
from app.repositories.scan_result import ScanResultRepository
from app.repositories.failed_scan import FailedScanRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.services.build_service import BuildService

logger = logging.getLogger(__name__)


class SonarService:
    def __init__(self, db: Database):
        self.db = db
        self.scan_job_repo = ScanJobRepository(db)
        self.scan_result_repo = ScanResultRepository(db)
        self.failed_scan_repo = FailedScanRepository(db)
        self.repo_repo = ImportedRepositoryRepository(db)
        self.build_service = BuildService(db)

    def update_config(self, repo_id: str, config_content: str) -> bool:
        return self.repo_repo.update(repo_id, {"sonar_config": config_content})

    def get_config(self, repo_id: str) -> Optional[str]:
        repo = self.repo_repo.get(repo_id)
        return repo.sonar_config if repo else None

    def trigger_scan(self, build_id: str) -> ScanJob:
        from app.tasks.sonar import run_sonar_scan

        build = self.build_service.get_build_detail(build_id)
        if not build:
            raise ValueError("Build not found")

        repo_sample = self.db["build_samples"].find_one({"_id": ObjectId(build_id)})
        repo_id = str(repo_sample["repo_id"])

        job = ScanJob(
            repo_id=ObjectId(repo_id),
            build_id=ObjectId(build_id),
            commit_sha=build.commit_sha,
            status=ScanJobStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        created_job = self.scan_job_repo.create(job)

        # Trigger Celery task
        run_sonar_scan.delay(str(created_job.id))

        return created_job

    def retry_job(self, job_id: str, config_override: Optional[str] = None) -> ScanJob:
        from app.tasks.sonar import run_sonar_scan

        job = self.scan_job_repo.get(job_id)
        if not job:
            raise ValueError("Job not found")

        # If config override provided, save it to the failed scan record
        failed_scan = self.failed_scan_repo.get_by_job_id(job_id)
        if failed_scan and config_override:
            self.failed_scan_repo.update(
                str(failed_scan.id),
                {
                    "config_override": config_override,
                    "config_source": "text",
                    "status": ScanStatus.QUEUED,
                },
            )

        updated_job = self.scan_job_repo.update(
            job_id,
            {
                "status": ScanJobStatus.PENDING,
                "error_message": None,
                "updated_at": datetime.utcnow(),
            },
        )

        run_sonar_scan.delay(job_id)
        return updated_job

    def list_jobs(self, repo_id: str, skip: int = 0, limit: int = 20) -> dict:
        items = self.scan_job_repo.list_by_repo(repo_id, skip, limit)
        total = self.scan_job_repo.count_by_repo(repo_id)
        return {"items": items, "total": total}

    def list_results(self, repo_id: str, skip: int = 0, limit: int = 20) -> dict:
        items = self.scan_result_repo.list_by_repo(repo_id, skip, limit)
        total = self.scan_result_repo.count_by_repo(repo_id)
        return {"items": items, "total": total}

    def list_failed_scans(self, repo_id: str, skip: int = 0, limit: int = 20) -> dict:
        items = self.failed_scan_repo.list_by_repo(
            repo_id, status=ScanStatus.PENDING, skip=skip, limit=limit
        )
        total = self.failed_scan_repo.count_pending_by_repo(repo_id)
        return {"items": items, "total": total}

    def update_failed_scan_config(
        self, failed_scan_id: str, config_content: str
    ) -> FailedScan:
        updated = self.failed_scan_repo.update(
            failed_scan_id,
            {
                "config_override": config_content,
                "config_source": "text",
                "updated_at": datetime.utcnow(),
            },
        )
        return updated

    def retry_failed_scan(self, failed_scan_id: str) -> dict:
        """Retry a failed scan with its config override."""
        failed_scan = self.failed_scan_repo.get(failed_scan_id)
        if not failed_scan:
            raise ValueError("Failed scan not found")

        return self.retry_job(
            str(failed_scan.job_id), config_override=failed_scan.config_override
        )
