"""
SonarQube Celery Tasks for Enrichment Scans.

Tasks:
- start_sonar_scan_for_version_commit: Start async scan (dedicated queue)
- export_metrics_from_webhook: Handle webhook when scan completes
"""

import logging
from typing import Optional

from bson import ObjectId

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.integrations.tools.sonarqube.exporter import MetricsExporter
from app.integrations.tools.sonarqube.runner import SonarCommitRunner
from app.paths import WORKTREES_DIR
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.sonar_commit_scan import SonarCommitScanRepository

logger = logging.getLogger(__name__)


def get_worktree_path(raw_repo_id: str, commit_sha: str) -> Optional[str]:
    """
    Derive worktree path from raw_repo_id and commit_sha.

    Path format: WORKTREES_DIR / raw_repo_id / commit_sha[:12]
    """
    path = WORKTREES_DIR / raw_repo_id / commit_sha[:12]
    if path.exists():
        return str(path)
    return None


# =============================================================================
# SCAN TASK - Runs on dedicated sonar_scan queue
# =============================================================================


@celery_app.task(
    bind=True,
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
    component_key: str,
    config_content: str = None,
):
    """
    Start SonarQube scan for a commit in a dataset version.

    Creates/updates SonarCommitScan record for tracking.
    Webhook will backfill results to all builds with matching commit.

    Args:
        version_id: DatasetVersion ID
        commit_sha: Commit SHA to scan
        repo_full_name: Repository full name (owner/repo)
        raw_repo_id: RawRepository ID - used to derive worktree path
        component_key: SonarQube project key (format: reponame_commithash)
        config_content: Optional sonar-project.properties content
    """
    logger.info(f"Starting SonarQube scan for commit {commit_sha[:8]} in version {version_id[:8]}")

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
        logger.info(f"Scan already in progress for {component_key}")
        return {"status": "already_scanning", "component_key": component_key}

    # Derive worktree path from raw_repo_id
    worktree_path = get_worktree_path(raw_repo_id, commit_sha)
    if not worktree_path:
        error_msg = f"Worktree not found for {repo_full_name} @ {commit_sha[:8]}"
        logger.error(error_msg)
        scan_repo.mark_failed(scan_record.id, error_msg)
        raise ValueError(error_msg)

    # Mark as scanning
    scan_repo.mark_scanning(scan_record.id)

    try:
        project_key = component_key.rsplit("_", 1)[0]
        runner = SonarCommitRunner(project_key, raw_repo_id=raw_repo_id)
        runner.scan_commit(
            repo_url=f"https://github.com/{repo_full_name}.git",
            commit_sha=commit_sha,
            sonar_config_content=config_content,
            shared_worktree_path=worktree_path,
            full_name=repo_full_name,
        )

        logger.info(f"SonarQube scan initiated for {component_key}, waiting for webhook")
        return {"status": "scanning", "component_key": component_key}

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"SonarQube scan failed for {component_key}: {error_msg}")
        scan_repo.mark_failed(scan_record.id, error_msg)

        raise self.retry(
            exc=exc,
            countdown=min(60 * (2**self.request.retries), 1800),
            max_retries=2,
        ) from exc


# =============================================================================
# WEBHOOK HANDLER - Processes results when SonarQube analysis completes
# =============================================================================


@celery_app.task(
    bind=True,
    name="app.tasks.sonar.export_metrics_from_webhook",
    queue="processing",
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
            scan_repo.mark_failed(scan_record.id, f"Analysis failed: {analysis_status}")
            return {"status": "failed", "component_key": component_key}

        # Export metrics from SonarQube API
        exporter = MetricsExporter()
        raw_metrics = exporter.collect_metrics(component_key)

        if not raw_metrics:
            logger.warning(f"No metrics available for {component_key}")
            scan_repo.mark_failed(scan_record.id, "No metrics available")
            return {"status": "no_metrics", "component_key": component_key}

        # Get version to filter metrics
        version = version_repo.find_by_id(str(scan_record.dataset_version_id))
        if not version:
            logger.error(f"Version {scan_record.dataset_version_id} not found")
            scan_repo.mark_failed(scan_record.id, "Version not found")
            return {"status": "version_not_found", "component_key": component_key}

        # Filter metrics based on user selection
        selected_metrics = version.scan_metrics.get("sonarqube", [])
        filtered_metrics = _filter_metrics_by_selection(raw_metrics, selected_metrics)

        # Backfill to all builds in version with matching commit
        updated_count = enrichment_build_repo.backfill_by_commit_in_version(
            version_id=scan_record.dataset_version_id,
            commit_sha=scan_record.commit_sha,
            scan_features=filtered_metrics,
            prefix="sonar_",
        )

        # Mark completed
        scan_repo.mark_completed(scan_record.id, raw_metrics, updated_count)

        logger.info(
            f"SonarQube metrics backfilled to {updated_count} builds "
            f"for commit {scan_record.commit_sha[:8]} ({len(filtered_metrics)} metrics)"
        )

        return {
            "status": "success",
            "builds_updated": updated_count,
            "metrics_count": len(filtered_metrics),
        }

    except Exception as exc:
        logger.error(f"Failed to export metrics for {component_key}: {exc}")
        scan_repo.mark_failed(scan_record.id, str(exc))
        raise


def _filter_metrics_by_selection(
    raw_metrics: dict,
    selected_metrics: list,
) -> dict:
    """Filter raw metrics based on user's selected metric list."""
    if not selected_metrics:
        return raw_metrics

    filtered = {}
    for key, value in raw_metrics.items():
        if key in selected_metrics or f"sonar_{key}" in selected_metrics:
            filtered[key] = value

    logger.debug(f"Filtered {len(raw_metrics)} -> {len(filtered)} metrics")
    return filtered
