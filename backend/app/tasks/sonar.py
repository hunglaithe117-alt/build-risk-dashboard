"""
SonarQube Celery Tasks for Enrichment Scans.

Tasks:
- start_sonar_scan_for_version_commit: Start async scan (dedicated queue)
- export_metrics_from_webhook: Handle webhook when scan completes
"""

import logging

from bson import ObjectId

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.integrations.tools.sonarqube.exporter import MetricsExporter
from app.integrations.tools.sonarqube.tool import SonarQubeTool
from app.paths import get_worktree_path
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.sonar_commit_scan import SonarCommitScanRepository
from app.tasks.base import PipelineTask
from app.tasks.shared.events import publish_scan_update

logger = logging.getLogger(__name__)


# SCAN TASK - Runs on dedicated sonar_scan queue
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.sonar.start_sonar_scan_for_version_commit",
    queue="sonar_scan",
    soft_time_limit=1800,
    time_limit=2100,
)
def start_sonar_scan_for_version_commit(
    self,
    version_id: str,
    commit_sha: str,
    repo_full_name: str,
    raw_repo_id: str,
    github_repo_id: int,
    component_key: str,
    config_file_path: str = "",
    correlation_id: str = "",
):
    """
    Start SonarQube scan for a commit in a dataset version.

    Creates/updates SonarCommitScan record for tracking.
    Webhook will backfill results to all builds with matching commit.

    Args:
        version_id: DatasetVersion ID
        commit_sha: Commit SHA to scan
        repo_full_name: Repository full name (owner/repo)
        raw_repo_id: RawRepository MongoDB ID
        github_repo_id: GitHub's internal repository ID for paths
        component_key: SonarQube project key (format: reponame_commithash)
        config_file_path: External config file path (sonar-project.properties)
        correlation_id: Correlation ID for tracing
    """
    from pathlib import Path

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(
        f"{corr_prefix} Starting SonarQube scan for {commit_sha[:8]} in version {version_id[:8]}"
    )

    db = get_database()
    scan_repo = SonarCommitScanRepository(db)

    # Create or get scan record (stores raw_repo_id for retry)
    scan_record = scan_repo.create_or_get(
        version_id=ObjectId(version_id),
        commit_sha=commit_sha,
        repo_full_name=repo_full_name,
        raw_repo_id=ObjectId(raw_repo_id),
        component_key=component_key,
    )

    # Check if already scanning
    if scan_record.status.value == "scanning":
        logger.info(f"{corr_prefix} Scan already in progress for {component_key}")
        return {"status": "already_scanning", "component_key": component_key}

    # Get worktree path using github_repo_id
    worktree_path = get_worktree_path(github_repo_id, commit_sha)
    if not worktree_path.exists():
        error_msg = f"Worktree not found for {repo_full_name} @ {commit_sha[:8]}"
        logger.error(error_msg)
        scan_repo.mark_failed(scan_record.id, error_msg)
        raise ValueError(error_msg)

    worktree_path_str = str(worktree_path)

    # Mark as scanning
    scan_repo.mark_scanning(scan_record.id)

    # Publish scanning status
    publish_scan_update(
        version_id=version_id,
        scan_id=str(scan_record.id),
        commit_sha=commit_sha,
        tool_type="sonarqube",
        status="scanning",
    )

    try:
        project_key = component_key.rsplit("_", 1)[0]
        sonar_tool = SonarQubeTool(project_key=project_key, github_repo_id=github_repo_id)
        sonar_tool.scan_commit(
            commit_sha=commit_sha,
            full_name=repo_full_name,
            config_file_path=Path(config_file_path) if config_file_path else None,
            shared_worktree_path=worktree_path_str,
        )

        logger.info(
            f"{corr_prefix} SonarQube scan initiated for {component_key}, waiting for webhook"
        )
        return {"status": "scanning", "component_key": component_key}

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"{corr_prefix} SonarQube scan failed for {component_key}: {error_msg}")
        scan_repo.mark_failed(scan_record.id, error_msg)

        # Publish failed status
        publish_scan_update(
            version_id=version_id,
            scan_id=str(scan_record.id),
            commit_sha=commit_sha,
            tool_type="sonarqube",
            status="failed",
            error=error_msg,
        )

        raise self.retry(
            exc=exc,
            countdown=min(60 * (2**self.request.retries), 1800),
            max_retries=2,
        ) from exc


# WEBHOOK HANDLER - Processes results when SonarQube analysis completes
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.sonar.export_metrics_from_webhook",
    queue="processing",
    soft_time_limit=120,
    time_limit=180,
)
def export_metrics_from_webhook(
    self,
    component_key: str,
    analysis_status: str,
):
    """
    Handle SonarQube webhook callback when analysis completes.

    Fetches metrics, filters by version config, and backfills to builds.

    Args:
        component_key: SonarQube component/project key
        analysis_status: Status from webhook ("SUCCESS", "FAILED", etc.)
    """
    logger.info(f"Processing SonarQube webhook for {component_key}, status={analysis_status}")

    db = get_database()
    scan_repo = SonarCommitScanRepository(db)
    version_repo = DatasetVersionRepository(db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(db)

    # Find scan record
    scan_record = scan_repo.find_by_component_key(component_key)
    if not scan_record:
        logger.warning(f"No scan record found for {component_key}")
        return {"status": "no_scan_record", "component_key": component_key}

    try:
        # Handle failed analysis
        if analysis_status != "SUCCESS":
            error_msg = f"Analysis failed: {analysis_status}"
            scan_repo.mark_failed(scan_record.id, error_msg)

            # Publish failed status
            publish_scan_update(
                version_id=str(scan_record.dataset_version_id),
                scan_id=str(scan_record.id),
                commit_sha=scan_record.commit_sha,
                tool_type="sonarqube",
                status="failed",
                error=error_msg,
            )
            return {"status": "failed", "component_key": component_key}

        # Get version to determine which metrics to fetch
        version = version_repo.find_by_id(str(scan_record.dataset_version_id))
        if not version:
            logger.error(f"Version {scan_record.dataset_version_id} not found")
            scan_repo.mark_failed(scan_record.id, "Version not found")
            return {"status": "version_not_found", "component_key": component_key}

        # Get user's selected metrics (only fetch these from SonarQube API)
        selected_metrics = version.scan_metrics.get("sonarqube", [])

        # Export only selected metrics from SonarQube API (not all then filter)
        exporter = MetricsExporter()
        metrics = exporter.collect_metrics(
            component_key,
            selected_metrics=selected_metrics if selected_metrics else None,
        )

        if not metrics:
            logger.warning(f"No metrics available for {component_key}")
            scan_repo.mark_failed(scan_record.id, "No metrics available")
            return {"status": "no_metrics", "component_key": component_key}

        # Backfill to all builds in version with matching commit
        updated_count = enrichment_build_repo.backfill_by_commit_in_version(
            version_id=scan_record.dataset_version_id,
            commit_sha=scan_record.commit_sha,
            scan_features=metrics,
            prefix="sonar_",
        )

        # Mark completed (store raw metrics for debugging)
        scan_repo.mark_completed(scan_record.id, metrics, updated_count)

        logger.info(
            f"SonarQube metrics backfilled to {updated_count} builds "
            f"for commit {scan_record.commit_sha[:8]} ({len(metrics)} metrics)"
        )

        # Publish completed status
        publish_scan_update(
            version_id=str(scan_record.dataset_version_id),
            scan_id=str(scan_record.id),
            commit_sha=scan_record.commit_sha,
            tool_type="sonarqube",
            status="completed",
            metrics=metrics,
            builds_affected=updated_count,
        )

        return {
            "status": "success",
            "builds_updated": updated_count,
            "metrics_count": len(metrics),
        }

    except Exception as exc:
        logger.error(f"Failed to export metrics for {component_key}: {exc}")
        scan_repo.mark_failed(scan_record.id, str(exc))

        # Publish failed status
        publish_scan_update(
            version_id=str(scan_record.dataset_version_id),
            scan_id=str(scan_record.id),
            commit_sha=scan_record.commit_sha,
            tool_type="sonarqube",
            status="failed",
            error=str(exc),
        )
        raise
