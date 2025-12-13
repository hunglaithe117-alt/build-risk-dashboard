"""
Trivy Celery Tasks.

Tasks:
- start_trivy_scan: Async Trivy scan for large repositories
"""

import logging
import time
from datetime import datetime, timezone

from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.database.mongo import get_database
from app.repositories.enrichment_build import EnrichmentBuildRepository
from app.repositories.model_build import ModelBuildRepository
from app.integrations.tools.trivy import TrivyTool

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.trivy.start_trivy_scan",
    queue="trivy_scan",  # Dedicated queue for security scanning
    soft_time_limit=600,  # 10 min soft limit
    time_limit=900,  # 15 min hard limit
)
def start_trivy_scan(
    self,
    build_id: str,
    build_type: str,
    worktree_path: str,
    commit_sha: str,
):
    """
    Run async Trivy scan for large repositories.

    Args:
        build_id: Build ID (ModelBuild or EnrichmentBuild)
        build_type: "model" or "enrichment"
        worktree_path: Path to git worktree to scan
        commit_sha: Commit SHA being scanned
    """
    logger.info(f"Starting async Trivy scan for build {build_id} at {commit_sha[:8]}")

    db = get_database()
    start_time = time.time()

    try:
        # Initialize Trivy tool
        trivy_tool = TrivyTool()

        # Run scan
        scan_result = trivy_tool.scan(
            target_path=worktree_path,
            scan_types=["vuln", "config", "secret"],
        )

        scan_duration_ms = scan_result.get(
            "scan_duration_ms", int((time.time() - start_time) * 1000)
        )

        if scan_result.get("status") == "failed":
            error_msg = scan_result.get("error", "Unknown error")
            logger.error(f"Trivy scan failed for {commit_sha[:8]}: {error_msg}")
            return {"status": "error", "error": error_msg}

        # Get metrics from scan result
        scan_metrics = scan_result.get("metrics", {})

        # Format features
        trivy_features = {
            "trivy_vuln_critical": scan_metrics.get("vuln_critical", 0),
            "trivy_vuln_high": scan_metrics.get("vuln_high", 0),
            "trivy_vuln_medium": scan_metrics.get("vuln_medium", 0),
            "trivy_vuln_low": scan_metrics.get("vuln_low", 0),
            "trivy_vuln_total": scan_metrics.get("vuln_total", 0),
            "trivy_misconfig_critical": scan_metrics.get("misconfig_critical", 0),
            "trivy_misconfig_high": scan_metrics.get("misconfig_high", 0),
            "trivy_misconfig_medium": scan_metrics.get("misconfig_medium", 0),
            "trivy_misconfig_low": scan_metrics.get("misconfig_low", 0),
            "trivy_misconfig_total": scan_metrics.get("misconfig_total", 0),
            "trivy_secrets_count": scan_metrics.get("secrets_count", 0),
            "trivy_scan_duration_ms": scan_duration_ms,
            "trivy_packages_scanned": scan_metrics.get("packages_scanned", 0),
            "trivy_files_scanned": scan_metrics.get("files_scanned", 0),
            "trivy_has_critical": scan_metrics.get("has_critical", False),
            "trivy_has_high": scan_metrics.get("has_high", False),
            "trivy_top_vulnerable_packages": scan_metrics.get(
                "top_vulnerable_packages", []
            ),
        }

        # Update build with features
        if build_type == "enrichment":
            build_repo = EnrichmentBuildRepository(db)
        else:
            build_repo = ModelBuildRepository(db)

        # Merge trivy features into existing features
        build = build_repo.find_by_id(build_id)
        if build:
            existing_features = build.features or {}
            existing_features.update(trivy_features)
            build_repo.update_one(
                build_id,
                {
                    "features": existing_features,
                    "trivy_scan_completed_at": datetime.now(timezone.utc),
                },
            )

        logger.info(
            f"Async Trivy scan completed for {commit_sha[:8]}: "
            f"{trivy_features.get('trivy_vuln_total', 0)} vulnerabilities in {scan_duration_ms}ms"
        )

        return {
            "status": "success",
            "build_id": build_id,
            "vuln_total": trivy_features.get("trivy_vuln_total", 0),
            "scan_duration_ms": scan_duration_ms,
        }

    except Exception as e:
        logger.error(f"Async Trivy scan failed for {build_id}: {e}")
        raise self.retry(
            exc=e,
            countdown=min(60 * (2**self.request.retries), 600),
            max_retries=2,
        )
