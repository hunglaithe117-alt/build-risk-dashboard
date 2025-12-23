"""
Trivy Celery Tasks for Enrichment Scans.

Tasks:
- start_trivy_scan_for_version_commit: Run Trivy scan on dedicated queue
"""

import logging
import time
from typing import Any, Dict, List

from bson import ObjectId

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.integrations.tools.trivy import TrivyTool
from app.paths import get_worktree_path
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.trivy_commit_scan import TrivyCommitScanRepository
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)


# TRIVY SCAN TASK - Runs on dedicated trivy_scan queue
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.trivy.start_trivy_scan_for_version_commit",
    queue="trivy_scan",
    soft_time_limit=600,
    time_limit=900,
)
def start_trivy_scan_for_version_commit(
    self,
    version_id: str,
    commit_sha: str,
    repo_full_name: str,
    raw_repo_id: str,
    github_repo_id: int,
    trivy_config: Dict[str, Any] = None,
    selected_metrics: List[str] = None,
):
    """
    Run Trivy scan for a commit in a dataset version.

    Creates/updates TrivyCommitScan record for tracking and retry.
    Results are backfilled to all enrichment builds with matching commit.

    Args:
        version_id: DatasetVersion ID
        commit_sha: Commit SHA being scanned
        repo_full_name: Repository full name (owner/repo)
        raw_repo_id: RawRepository MongoDB ID
        github_repo_id: GitHub's internal repository ID for paths
        trivy_config: Optional config override containing:
            - config_content: trivy.yaml content from UI (optional)
            - scanners: comma-separated list like "vuln,config,secret" (optional)
        selected_metrics: Optional list of metrics to filter
    """
    logger.info(f"Starting Trivy scan for commit {commit_sha[:8]} in version {version_id[:8]}")

    trivy_config = trivy_config or {}
    selected_metrics = selected_metrics or []

    db = get_database()
    trivy_scan_repo = TrivyCommitScanRepository(db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(db)

    # Create or get scan record (stores raw_repo_id for retry)
    scan_record = trivy_scan_repo.create_or_get(
        version_id=ObjectId(version_id),
        commit_sha=commit_sha,
        repo_full_name=repo_full_name,
        raw_repo_id=ObjectId(raw_repo_id),
        scan_config=trivy_config,
        selected_metrics=selected_metrics,
    )

    # Get worktree path using github_repo_id
    worktree_path = get_worktree_path(github_repo_id, commit_sha)
    if not worktree_path.exists():
        error_msg = f"Worktree not found for {repo_full_name} @ {commit_sha[:8]}"
        logger.error(error_msg)
        trivy_scan_repo.mark_failed(scan_record.id, error_msg)
        raise ValueError(error_msg)

    worktree_path_str = str(worktree_path)

    # Mark as scanning
    trivy_scan_repo.mark_scanning(scan_record.id)

    start_time = time.time()

    try:
        # Run Trivy scan with optional config override
        # If user provides trivy.yaml content, it will be written to worktree
        trivy_tool = TrivyTool()
        scan_result = trivy_tool.scan(
            target_path=worktree_path_str,
            scan_types=_parse_scan_types(trivy_config),
            config_content=trivy_config.get("config_content"),  # trivy.yaml content from UI
        )

        scan_duration_ms = scan_result.get(
            "scan_duration_ms", int((time.time() - start_time) * 1000)
        )

        if scan_result.get("status") == "failed":
            error_msg = scan_result.get("error", "Unknown error")
            logger.error(f"Trivy scan failed for {commit_sha[:8]}: {error_msg}")
            trivy_scan_repo.mark_failed(scan_record.id, error_msg)
            return {"status": "error", "error": error_msg}

        # Process and filter metrics
        raw_metrics = scan_result.get("metrics", {})
        raw_metrics["scan_duration_ms"] = scan_duration_ms

        filtered_metrics = _filter_trivy_metrics(raw_metrics, selected_metrics)

        # Backfill to all builds in version with matching commit
        updated_count = enrichment_build_repo.backfill_by_commit_in_version(
            version_id=ObjectId(version_id),
            commit_sha=commit_sha,
            scan_features=filtered_metrics,
            prefix="trivy_",
        )

        # Mark completed with results
        trivy_scan_repo.mark_completed(
            scan_id=scan_record.id,
            metrics=filtered_metrics,
            builds_affected=updated_count,
        )

        logger.info(
            f"Trivy scan completed for {commit_sha[:8]}: "
            f"{filtered_metrics.get('vuln_total', 0)} vulns, "
            f"backfilled to {updated_count} builds ({scan_duration_ms}ms)"
        )

        return {
            "status": "success",
            "builds_updated": updated_count,
            "vuln_total": filtered_metrics.get("vuln_total", 0),
            "scan_duration_ms": scan_duration_ms,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Trivy scan failed for {commit_sha[:8]}: {error_msg}")
        trivy_scan_repo.mark_failed(scan_record.id, error_msg)

        raise self.retry(
            exc=exc,
            countdown=min(60 * (2**self.request.retries), 600),
            max_retries=2,
        ) from exc


def _parse_scan_types(trivy_config: dict) -> List[str]:
    """Parse scan types from config, default to all types."""
    default_types = ["vuln", "config", "secret"]

    if not trivy_config.get("scanners"):
        return default_types

    scanners = trivy_config["scanners"]
    if isinstance(scanners, str):
        return [s.strip() for s in scanners.split(",")]
    return scanners


def _filter_trivy_metrics(
    raw_metrics: dict,
    selected_metrics: List[str],
) -> dict:
    """Filter raw Trivy metrics based on user-selected metric list."""
    if not selected_metrics:
        return raw_metrics

    filtered = {}
    for key, value in raw_metrics.items():
        if key in selected_metrics or f"trivy_{key}" in selected_metrics:
            filtered[key] = value

    logger.debug(f"Filtered Trivy {len(raw_metrics)} -> {len(filtered)} metrics")
    return filtered
