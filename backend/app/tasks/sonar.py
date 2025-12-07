import logging
from datetime import datetime
from bson import ObjectId

from app.celery_app import celery_app
from app.services.sonar.runner import SonarCommitRunner
from app.services.sonar.exporter import MetricsExporter
from app.database.mongo import get_db
from app.repositories.scan_job import ScanJobRepository
from app.repositories.scan_result import ScanResultRepository
from app.repositories.failed_scan import FailedScanRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.entities.scan_job import ScanJobStatus
from app.entities.failed_scan import FailedScan, ScanErrorType, ScanStatus
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.sonar.run_sonar_scan")
def run_sonar_scan(self, job_id: str):
    logger.info(f"Starting SonarQube scan job {job_id}")

    db = next(get_db())
    job_repo = ScanJobRepository(db)
    scan_result_repo = ScanResultRepository(db)
    failed_scan_repo = FailedScanRepository(db)
    repo_repo = ImportedRepositoryRepository(db)
    build_collection = db["build_samples"]

    job = job_repo.get(job_id)
    if not job:
        logger.error(f"ScanJob {job_id} not found")
        return

    # Update status to RUNNING
    job_repo.update(
        job_id,
        {
            "status": ScanJobStatus.RUNNING,
            "started_at": datetime.utcnow(),
            "worker_id": self.request.id,
        },
    )

    try:
        repo_doc = repo_repo.get(str(job.repo_id))
        if not repo_doc:
            raise ValueError("Repository not found")

        repo_url = repo_doc.html_url
        if not repo_url:
            raise ValueError("Repository URL not found")

        project_key_prefix = settings.SONAR_DEFAULT_PROJECT_KEY
        project_key = f"{project_key_prefix}_{repo_doc.name}"

        # Check for config override from failed scan
        config_content = repo_doc.sonar_config
        failed_scan = failed_scan_repo.get_by_job_id(job_id)
        if failed_scan and failed_scan.config_override:
            logger.info(f"Using config override from failed scan {failed_scan.id}")
            config_content = failed_scan.config_override

        # 2. Run Scan
        runner = SonarCommitRunner(project_key)
        component_key = runner.scan_commit(
            repo_url, job.commit_sha, sonar_config_content=config_content
        )

        # 3. Export Metrics
        exporter = MetricsExporter()
        metrics = exporter.collect_metrics(component_key)

        # 4. Store ScanResult
        scan_result_repo.upsert_by_job(
            job_id,
            {
                "repo_id": job.repo_id,
                "job_id": job.id,
                "sonar_project_key": component_key,
                "metrics": metrics,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )

        # 5. Update BuildSample (for backward compatibility)
        build_collection.update_one(
            {"_id": job.build_id},
            {
                "$set": {
                    "features.sonar_metrics": metrics,
                    "features.sonar_project_key": component_key,
                    "sonar_scan_status": "completed",
                }
            },
        )

        # 6. Update ScanJob
        job_repo.update(
            job_id,
            {
                "status": ScanJobStatus.SUCCESS,
                "finished_at": datetime.utcnow(),
                "sonar_component_key": component_key,
            },
        )

        # 7. Resolve FailedScan if exists
        if failed_scan:
            failed_scan_repo.update(
                str(failed_scan.id),
                {"status": ScanStatus.RESOLVED, "resolved_at": datetime.utcnow()},
            )

        logger.info(f"Completed SonarQube scan job {job_id}")
        return {"status": "success", "component_key": component_key}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"SonarQube scan failed for job {job_id}: {error_msg}")

        # Update job status
        job_repo.update(
            job_id,
            {
                "status": ScanJobStatus.FAILED,
                "finished_at": datetime.utcnow(),
                "error_message": error_msg,
            },
        )

        # Update build sample status
        build_collection.update_one(
            {"_id": job.build_id},
            {"$set": {"sonar_scan_status": "failed", "sonar_scan_error": error_msg}},
        )

        # Create or update FailedScan record if not already retrying
        existing_failed = failed_scan_repo.get_by_job_id(job_id)
        if not existing_failed:
            failed_scan = FailedScan(
                repo_id=job.repo_id,
                build_id=job.build_id,
                job_id=job.id,
                commit_sha=job.commit_sha,
                reason=error_msg,
                error_type=ScanErrorType.SCAN_ERROR,
                status=ScanStatus.PENDING,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            failed_scan_repo.create(failed_scan)
        else:
            # Increment retry count
            failed_scan_repo.update(
                str(existing_failed.id),
                {
                    "retry_count": (existing_failed.retry_count or 0) + 1,
                    "reason": error_msg,
                    "status": ScanStatus.PENDING,
                    "updated_at": datetime.utcnow(),
                },
            )

        # Retry with exponential backoff
        raise self.retry(
            exc=e, countdown=min(60 * (2**self.request.retries), 3600), max_retries=3
        )


@celery_app.task(bind=True, name="app.tasks.sonar.export_metrics_from_webhook")
def export_metrics_from_webhook(self, component_key: str, job_id: str):
    logger.info(f"Exporting metrics for {component_key} from webhook (job {job_id})")

    db = next(get_db())
    job_repo = ScanJobRepository(db)
    scan_result_repo = ScanResultRepository(db)
    failed_scan_repo = FailedScanRepository(db)
    build_collection = db["build_samples"]

    job = job_repo.get(job_id)
    if not job:
        logger.error(f"ScanJob {job_id} not found")
        return

    try:
        # Export metrics
        exporter = MetricsExporter()
        metrics = exporter.collect_metrics(component_key)

        if not metrics:
            raise RuntimeError(f"No metrics available for {component_key}")

        # Store ScanResult
        scan_result_repo.upsert_by_job(
            job_id,
            {
                "repo_id": job.repo_id,
                "job_id": job.id,
                "sonar_project_key": component_key,
                "metrics": metrics,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
        )

        # Update BuildSample
        build_collection.update_one(
            {"_id": job.build_id},
            {
                "$set": {
                    "features.sonar_metrics": metrics,
                    "features.sonar_project_key": component_key,
                    "sonar_scan_status": "completed",
                }
            },
        )

        # Update ScanJob
        job_repo.update(
            job_id,
            {
                "status": ScanJobStatus.SUCCESS,
                "finished_at": datetime.utcnow(),
            },
        )

        # Resolve FailedScan if exists
        failed_scan = failed_scan_repo.get_by_job_id(job_id)
        if failed_scan:
            failed_scan_repo.update(
                str(failed_scan.id),
                {"status": ScanStatus.RESOLVED, "resolved_at": datetime.utcnow()},
            )

        logger.info(f"Successfully exported metrics for {component_key}")
        return {"status": "success", "metrics_count": len(metrics)}

    except Exception as e:
        logger.error(f"Failed to export metrics for {component_key}: {e}")
        job_repo.update(
            job_id,
            {
                "status": ScanJobStatus.FAILED,
                "finished_at": datetime.utcnow(),
                "error_message": f"Metrics export failed: {str(e)}",
            },
        )
        raise
