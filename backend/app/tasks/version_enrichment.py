"""
Version Enrichment Task - Process dataset versions.

This task runs the feature extraction pipeline for a specific dataset version.
"""

import logging
import os
from datetime import datetime, timezone
from typing import List

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.entities.dataset_version import VersionStatus
from app.repositories.dataset_version import DatasetVersionRepository
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.version_enrichment.enrich_version_task",
    queue="enrichment",
    soft_time_limit=7200,  # 2 hours
    time_limit=7500,  # 2.5 hours hard limit
)
def enrich_version_task(self, version_id: str):
    """
    Enrich a dataset version with selected features.

    This task:
    1. Loads the version configuration
    2. Reads the original CSV
    3. Runs the feature extraction pipeline for each row
    4. Writes the enriched CSV
    5. Updates version status

    Args:
        version_id: ID of the DatasetVersion to process
    """
    logger.info(f"Starting version enrichment task for {version_id}")

    db = get_database()
    version_repo = DatasetVersionRepository(db)
    dataset_service = DatasetService(db)

    # Load version
    version = version_repo.find_by_id(version_id)
    if not version:
        logger.error(f"Version {version_id} not found")
        return {"status": "error", "error": "Version not found"}

    # Mark as started
    version_repo.mark_started(version_id, task_id=self.request.id)

    try:
        # Load dataset
        dataset = dataset_service.get_dataset_by_id(version.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {version.dataset_id} not found")

        # Get total rows
        total_rows = dataset.rows or 0
        version_repo.update_one(version_id, {"total_rows": total_rows})

        # TODO: Implement actual enrichment logic
        # For now, this is a placeholder that simulates progress

        import time
        from app.config import settings

        # Get the uploaded CSV path
        csv_path = dataset.file_path
        if not csv_path or not os.path.exists(csv_path):
            raise ValueError(f"Dataset file not found: {csv_path}")

        # Read CSV
        import pandas as pd

        df = pd.read_csv(csv_path)

        # Get mapped columns
        build_id_col = (
            dataset.mapped_fields.get("build_id") if dataset.mapped_fields else None
        )
        repo_col = (
            dataset.mapped_fields.get("repo_name") if dataset.mapped_fields else None
        )

        if not build_id_col or not repo_col:
            raise ValueError("Dataset must have build_id and repo_name columns mapped")

        # Process rows (simplified for now)
        processed = 0
        enriched = 0
        failed = 0

        # Initialize empty columns for selected features
        for feature in version.selected_features:
            df[feature] = None

        # For each row, we would normally run the pipeline
        # This is a simplified version that just marks progress
        for idx, row in df.iterrows():
            try:
                # TODO: Actually run pipeline here
                # For now, just simulate
                processed += 1
                enriched += 1

                # Update progress every 10 rows
                if processed % 10 == 0:
                    version_repo.update_progress(
                        version_id,
                        processed_rows=processed,
                        enriched_rows=enriched,
                        failed_rows=failed,
                    )

            except Exception as e:
                processed += 1
                failed += 1
                version_repo.update_progress(
                    version_id,
                    processed_rows=processed,
                    enriched_rows=enriched,
                    failed_rows=failed,
                    row_error={"row_index": idx, "error": str(e)},
                )

        # Final progress update
        version_repo.update_progress(
            version_id,
            processed_rows=processed,
            enriched_rows=enriched,
            failed_rows=failed,
        )

        # Write output CSV
        output_dir = os.path.join(settings.DATA_DIR, "enriched", version.dataset_id)
        os.makedirs(output_dir, exist_ok=True)

        output_filename = f"enriched_v{version.version_number}.csv"
        output_path = os.path.join(output_dir, output_filename)

        df.to_csv(output_path, index=False)
        file_size = os.path.getsize(output_path)

        # Mark as completed
        version_repo.mark_completed(
            version_id,
            file_path=output_path,
            file_name=output_filename,
            file_size_bytes=file_size,
        )

        logger.info(
            f"Version enrichment completed: {version_id}, "
            f"{enriched}/{total_rows} rows enriched"
        )

        return {
            "status": "completed",
            "version_id": version_id,
            "enriched_rows": enriched,
            "failed_rows": failed,
            "output_file": output_path,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Version enrichment failed: {error_msg}")
        version_repo.mark_failed(version_id, error_msg)

        # Re-raise for Celery retry logic
        raise self.retry(
            exc=e,
            countdown=min(60 * (2**self.request.retries), 1800),
            max_retries=2,
        )
