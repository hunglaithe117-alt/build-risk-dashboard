"""
SonarQube Celery Tasks.

Tasks:
- start_sonar_scan: Start async SonarQube scan (CPU-intensive, dedicated queue)
- export_metrics_from_webhook: Handle webhook callback when scan completes
"""

import logging
from datetime import datetime, timezone

from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.database.mongo import get_database
from app.entities.sonar_scan_pending import SonarScanPending, ScanPendingStatus
from app.repositories.sonar_scan_pending import SonarScanPendingRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.services.sonar.exporter import MetricsExporter
from app.services.sonar.runner import SonarCommitRunner

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.sonar.start_sonar_scan",
    queue="sonar_scan",  # Dedicated CPU-intensive queue
    soft_time_limit=1800,  # 30 min soft limit
    time_limit=2100,  # 35 min hard limit
)
def start_sonar_scan(
    self,
    build_id: str,
    build_type: str,
    repo_url: str,
    commit_sha: str,
    component_key: str,
    config_content: str = None,
    shared_worktree_path: str = None,
):
    """
    Start SonarQube scan for a commit (CPU-intensive).

    This task:
    1. Creates a pending scan record
    2. Runs sonar-scanner
    3. Webhook will handle metrics export when done

    Args:
        build_id: Build ID (ModelBuild or EnrichmentBuild)
        build_type: "model" or "enrichment"
        repo_url: Repository URL to clone
        commit_sha: Commit SHA to scan
        component_key: SonarQube component key
        config_content: Optional sonar-project.properties content
        shared_worktree_path: Optional path to shared worktree from pipeline
    """
    logger.info(f"Starting SonarQube scan for {component_key}")

    db = get_database()
    pending_repo = SonarScanPendingRepository(db)

    # Check if already pending
    existing = pending_repo.find_pending_by_component_key(component_key)
    if existing:
        logger.info(f"Scan already in progress for {component_key}")
        return {"status": "already_pending", "component_key": component_key}

    # Create pending record
    pending = SonarScanPending(
        build_id=ObjectId(build_id),
        build_type=build_type,
        component_key=component_key,
        commit_sha=commit_sha,
        repo_url=repo_url,
        status=ScanPendingStatus.SCANNING,
    )
    pending = pending_repo.insert_one(pending)

    try:
        # Get project key from component key (component_key = project_key_commit_sha)
        project_key = component_key.rsplit("_", 1)[0]

        # Run scanner (use shared worktree if available)
        runner = SonarCommitRunner(project_key)
        runner.scan_commit(
            repo_url,
            commit_sha,
            sonar_config_content=config_content,
            shared_worktree_path=shared_worktree_path,
        )

        logger.info(
            f"SonarQube scan completed for {component_key}, waiting for webhook"
        )
        return {"status": "scanning", "component_key": component_key}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"SonarQube scan failed for {component_key}: {error_msg}")

        # Mark as failed
        pending_repo.mark_failed(pending.id, error_msg)

        # Retry with exponential backoff
        raise self.retry(
            exc=e,
            countdown=min(60 * (2**self.request.retries), 1800),
            max_retries=2,
        )


@celery_app.task(
    bind=True,
    name="app.tasks.sonar.export_metrics_from_webhook",
    queue="data_processing",
)
def export_metrics_from_webhook(self, component_key: str, build_id: str = None):
    """
    Handle SonarQube webhook callback when scan completes.

    This is called by the webhook handler when SonarQube finishes analysis.
    Fetches metrics and updates the associated build.

    Args:
        component_key: SonarQube project/component key
        build_id: Optional build ID to update (deprecated, use pending record)
    """
    logger.info(f"Exporting metrics for {component_key} from webhook")

    db = get_database()
    pending_repo = SonarScanPendingRepository(db)

    # Find pending scan
    pending = pending_repo.find_pending_by_component_key(component_key)

    try:
        # Export metrics from SonarQube API
        exporter = MetricsExporter()
        metrics = exporter.collect_metrics(component_key)

        if not metrics:
            logger.warning(f"No metrics available for {component_key}")
            if pending:
                pending_repo.mark_failed(pending.id, "No metrics available")
            return {"status": "no_metrics", "component_key": component_key}

        # Convert to sonar_* feature format
        sonar_features = {f"sonar_{k}": v for k, v in metrics.items()}

        # Update build features if pending record exists
        if pending:
            if pending.build_type == "enrichment":
                build_repo = DatasetEnrichmentBuildRepository(db)
            else:
                build_repo = ModelTrainingBuildRepository(db)

            # Update build with sonar features
            build_repo.update_one(
                str(pending.build_id),
                {
                    "features": sonar_features,
                    "extraction_status": "completed",
                },
            )

            # Mark pending as completed
            pending_repo.mark_completed(pending.id, metrics)

            logger.info(
                f"Updated {pending.build_type} build {pending.build_id} with "
                f"{len(metrics)} sonar features"
            )
        else:
            logger.warning(f"No pending scan found for {component_key}")

        logger.info(f"Successfully exported {len(metrics)} metrics for {component_key}")
        return {"status": "success", "metrics_count": len(metrics)}

    except Exception as e:
        logger.error(f"Failed to export metrics for {component_key}: {e}")
        if pending:
            pending_repo.mark_failed(pending.id, str(e))
        raise
