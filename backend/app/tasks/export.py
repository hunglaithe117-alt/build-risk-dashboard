"""
Export Celery Task - Background job for large dataset exports.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery_app
from app.tasks.base import PipelineTask
from app.services.export_service import ExportService
from app.entities.export_job import ExportStatus

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.export.run_export_job",
    queue="export",
)
def run_export_job(self, job_id: str):
    """
    Run export job in background.

    This task:
    1. Updates job status to "processing"
    2. Counts total rows
    3. Writes export file with progress updates
    4. Updates job with completed status and file info
    """
    service = ExportService(self.db)
    job = service.job_repo.find_by_id(job_id)

    if not job:
        logger.error(f"Export job {job_id} not found")
        return {"status": "error", "message": "Job not found"}

    try:
        # Update status to processing
        service.job_repo.update_status(job_id, ExportStatus.PROCESSING.value)

        # Count total rows
        total = service.estimate_row_count(
            str(job.repo_id),
            job.start_date,
            job.end_date,
            job.build_status,
        )
        service.job_repo.update_status(
            job_id, ExportStatus.PROCESSING.value, total_rows=total
        )

        logger.info(f"Starting export job {job_id}: {total} rows, format={job.format}")

        # Progress callback to update processed count
        def on_progress(processed: int):
            service.job_repo.update_progress(job_id, processed)

        # Write export file
        file_path = service.write_export_file(job, progress_callback=on_progress)

        # Get file size
        file_size = file_path.stat().st_size

        # Update job as completed
        service.job_repo.update_status(
            job_id,
            ExportStatus.COMPLETED.value,
            file_path=str(file_path),
            file_size=file_size,
            completed_at=datetime.now(timezone.utc),
            processed_rows=total,
        )

        logger.info(
            f"Export job {job_id} completed: {total} rows, "
            f"size={file_size / 1024:.1f}KB"
        )

        return {
            "status": "completed",
            "file_path": str(file_path),
            "rows": total,
            "size": file_size,
        }

    except Exception as e:
        logger.error(f"Export job {job_id} failed: {e}", exc_info=True)

        service.job_repo.update_status(
            job_id,
            ExportStatus.FAILED.value,
            error_message=str(e),
        )

        return {"status": "failed", "error": str(e)}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.export.cleanup_old_exports",
    queue="maintenance",
)
def cleanup_old_exports(self, days: int = 7):
    """
    Cleanup old export files and job records.

    Run periodically via Celery beat.
    """
    from app.services.export_service import EXPORT_DIR

    service = ExportService(self.db)

    # Delete old job records
    deleted_count = service.job_repo.delete_old_jobs(days)
    logger.info(f"Deleted {deleted_count} old export job records")

    # Delete orphaned export files
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    files_deleted = 0

    for file_path in EXPORT_DIR.glob("*.*"):
        if file_path.stat().st_mtime < cutoff:
            try:
                file_path.unlink()
                files_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete {file_path}: {e}")

    logger.info(f"Deleted {files_deleted} old export files")

    return {
        "jobs_deleted": deleted_count,
        "files_deleted": files_deleted,
    }
