"""
Export Celery Task - Background job for large dataset exports.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.celery_app import celery_app
from app.config import settings
from app.entities.export_job import ExportStatus
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)

# Export directory
EXPORT_DIR = Path(settings.DATA_DIR) / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.export.process_export_job",
    queue="processing",
    soft_time_limit=600,
    time_limit=900,
)
def process_export_job(self, job_id: str):
    """
    Run export job in background.

    This task:
    1. Updates job status to "processing"
    2. Gets cursor from repository
    3. Writes export file with progress updates
    4. Updates job with completed status and file info
    """
    from bson import ObjectId

    from app.repositories.export_job import ExportJobRepository
    from app.repositories.model_training_build import ModelTrainingBuildRepository
    from app.utils.export_utils import format_feature_row, write_csv_file, write_json_file

    job_repo = ExportJobRepository(self.db)
    job = job_repo.find_by_id(job_id)

    if not job:
        logger.error(f"Export job {job_id} not found")
        return {"status": "error", "message": "Job not found"}

    try:
        # Update status to processing
        job_repo.update_status(job_id, ExportStatus.PROCESSING.value)

        build_repo = ModelTrainingBuildRepository(self.db)

        # Count total rows
        total = build_repo.count_for_export(
            ObjectId(job.repo_id),
            job.start_date,
            job.end_date,
            job.build_status,
        )
        job_repo.update_status(job_id, ExportStatus.PROCESSING.value, total_rows=total)

        logger.info(f"Starting export job {job_id}: {total} rows, format={job.format}")

        # Progress callback to update processed count
        def on_progress(processed: int):
            job_repo.update_progress(job_id, processed)

        # Get cursor for export
        cursor = build_repo.get_for_export(
            ObjectId(job.repo_id),
            job.start_date,
            job.end_date,
            job.build_status,
        )

        # Get all feature keys for consistent columns (CSV)
        all_feature_keys = None
        if job.format == "csv" and not job.features:
            all_feature_keys = build_repo.get_all_feature_keys(
                ObjectId(job.repo_id),
                job.start_date,
                job.end_date,
                job.build_status,
            )

        # Write export file
        file_path = EXPORT_DIR / f"{job_id}.{job.format}"

        if job.format == "csv":
            write_csv_file(
                file_path, cursor, format_feature_row, job.features, all_feature_keys, on_progress
            )
        else:
            write_json_file(file_path, cursor, format_feature_row, job.features, on_progress)

        # Get file size
        file_size = file_path.stat().st_size

        # Update job as completed
        job_repo.update_status(
            job_id,
            ExportStatus.COMPLETED.value,
            file_path=str(file_path),
            file_size=file_size,
            completed_at=datetime.now(timezone.utc),
            processed_rows=total,
        )

        logger.info(
            f"Export job {job_id} completed: {total} rows, " f"size={file_size / 1024:.1f}KB"
        )

        return {
            "status": "completed",
            "file_path": str(file_path),
            "rows": total,
            "size": file_size,
        }

    except Exception as e:
        logger.error(f"Export job {job_id} failed: {e}", exc_info=True)

        job_repo.update_status(
            job_id,
            ExportStatus.FAILED.value,
            error_message=str(e),
        )

        return {"status": "failed", "error": str(e)}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.export.cleanup_old_exports",
    queue="processing",
    soft_time_limit=120,
    time_limit=180,
)
def cleanup_old_exports(self, days: int = 7):
    """
    Cleanup old export files and job records.

    Run periodically via Celery beat.
    """
    from app.repositories.export_job import ExportJobRepository

    job_repo = ExportJobRepository(self.db)

    # Delete old job records
    deleted_count = job_repo.delete_old_jobs(days)
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
