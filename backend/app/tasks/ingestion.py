"""Ingestion tasks for repository backfill"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from app.celery_app import celery_app
from app.celery_app import celery_app
from app.services.pipeline_store_service import PipelineStore
from app.services.github.github_client import get_app_github_client
from app.repositories.scan_job import ScanJobRepository
from app.tasks.base import PipelineTask
from app.services.pipeline_exceptions import PipelineRateLimitError

logger = logging.getLogger(__name__)

import os
from pathlib import Path

LOG_DIR = Path("job_logs")
LOG_DIR.mkdir(exist_ok=True)


@celery_app.task(
    bind=True, base=PipelineTask, name="app.tasks.ingestion.trigger_initial_scan"
)
def trigger_initial_scan(self: PipelineTask, repo_id: str) -> Dict[str, Any]:
    """
    Start the initial scan (backfill) for a repository.
    1. Create/Update InitialScanJob
    2. List past workflow runs via GitHub API
    3. Enqueue processing for each run
    """
    store = PipelineStore(self.db)
    repo = store.get_repository(repo_id)
    if not repo:
        return {"status": "error", "message": "Repository not found"}

    scan_repo = ScanJobRepository(self.db)

    # Check for existing active job
    job = scan_repo.get_active_job(repo_id)
    if not job:
        job = scan_repo.create_job(repo_id)

    job_id = str(job["_id"])
    scan_repo.update_progress(job_id, status="running", phase="discovering_builds")

    try:
        installation_id = repo.get("installation_id")
        full_name = repo.get("full_name")

        # Enforce App auth for backfill
        if not installation_id:
            raise ValueError(
                "Repository missing installation_id. Cannot perform backfill without App installation."
            )

        gh_cm = get_app_github_client(self.db, installation_id)

        with gh_cm as gh:
            # List workflow runs
            # We might want to filter by branch or event if needed, but for backfill we usually want everything or last N months.
            # Let's fetch last 100 runs for now to start.
            runs = gh.list_workflow_runs(full_name, params={"per_page": 100})

            scan_repo.update_progress(job_id, total_runs=len(runs))

            for run in runs:
                # Enqueue processing for each run
                process_workflow_run.delay(repo_id, run)

            scan_repo.update_progress(job_id, status="completed", phase="finalizing")
    except PipelineRateLimitError as e:
        # Retry after the specified wait time
        wait = e.retry_after if e.retry_after else 60
        logger.warning(
            "Rate limit hit in trigger_initial_scan. Retrying in %s seconds.", wait
        )
        raise self.retry(exc=e, countdown=wait)
    except Exception as e:
        scan_repo.update_progress(job_id, status="failed", error=str(e))
        raise e

    return {
        "status": "completed",
        "job_id": job_id,
        "runs_found": len(runs) if "runs" in locals() else 0,
    }


@celery_app.task(
    bind=True, base=PipelineTask, name="app.tasks.ingestion.process_workflow_run"
)
def process_workflow_run(
    self: PipelineTask, repo_id: str, run: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process a single workflow run:
    1. Fetch workflow jobs
    2. Download logs for each job
    3. (Future) Parse logs and create BuildSnapshot
    """
    store = PipelineStore(self.db)
    repo = store.get_repository(repo_id)
    if not repo:
        return {"status": "error", "message": "Repository not found"}

    full_name = repo.get("full_name")
    installation_id = repo.get("installation_id")
    run_id = run.get("id")

    if not installation_id:
        raise ValueError(f"Repository {full_name} missing installation_id")

    try:
        with get_app_github_client(self.db, installation_id) as gh:
            # 1. Fetch workflow jobs
            jobs = gh.list_workflow_jobs(full_name, run_id)

            logs_collected = 0
            for job in jobs:
                job_id = job.get("id")
                # 2. Download logs for each job
                try:
                    # Check if logs are available first to avoid 404s or wasted bandwidth
                    # But download_job_logs handles errors too.
                    log_content = gh.download_job_logs(full_name, job_id)
                    if log_content:
                        logs_collected += 1
                        # Save log to file
                        log_path = LOG_DIR / str(repo_id) / str(run_id)
                        log_path.mkdir(parents=True, exist_ok=True)
                        file_path = log_path / f"{job_id}.log"
                        with open(file_path, "wb") as f:
                            f.write(log_content)
                except Exception as e:
                    logger.error(
                        "Failed to download logs for job %s in run %s (repo: %s): %s",
                        job_id,
                        run_id,
                        full_name,
                        str(e),
                        exc_info=True,
                    )
    except PipelineRateLimitError as e:
        wait = e.retry_after if e.retry_after else 60
        logger.warning(
            "Rate limit hit in process_workflow_run. Retrying in %s seconds.", wait
        )
        raise self.retry(exc=e, countdown=wait)

    return {
        "repo_id": repo_id,
        "run_id": run_id,
        "jobs_processed": len(jobs),
        "logs_collected": logs_collected,
    }
