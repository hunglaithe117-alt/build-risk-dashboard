"""
Trivy Vulnerability Node - Auto-extracts all security vulnerabilities.

Scans the repository at build commit using Trivy and extracts:
- Vulnerability counts by severity
- Misconfiguration counts
- Secret detections
- License issues
"""

import logging
import time
from typing import Any, Dict, Set

from app.pipeline.extract_nodes import FeatureNode
from app.pipeline.core.context import ExecutionContext
from app.pipeline.core.registry import register_feature
from app.pipeline.resources import ResourceNames
from app.config import settings

logger = logging.getLogger(__name__)

TRIVY_FEATURE_NAMES: Set[str] = {
    # Vulnerability counts by severity
    "trivy_vuln_critical",
    "trivy_vuln_high",
    "trivy_vuln_medium",
    "trivy_vuln_low",
    "trivy_vuln_total",
    # Misconfiguration counts
    "trivy_misconfig_critical",
    "trivy_misconfig_high",
    "trivy_misconfig_medium",
    "trivy_misconfig_low",
    "trivy_misconfig_total",
    # Secret detection
    "trivy_secrets_count",
    # Aggregated metrics
    "trivy_scan_duration_ms",
    "trivy_packages_scanned",
    "trivy_files_scanned",
    "trivy_has_critical",
    "trivy_has_high",
    # Top vulnerable packages (JSON list)
    "trivy_top_vulnerable_packages",
}

from app.pipeline.feature_metadata.trivy import TRIVY_METADATA


@register_feature(
    name="trivy_vulnerability_scan",
    group="security",
    description="Security vulnerability scanning",
    requires_resources={ResourceNames.GIT_REPO, "trivy_client"},
    provides=TRIVY_FEATURE_NAMES,
    feature_metadata=TRIVY_METADATA,
)
class TrivyVulnerabilityNode(FeatureNode):
    """
    Trivy vulnerability scanner feature node.

    Uses shared worktree from GitRepoProvider for scanning.
    Supports both sync (inline) and async (Celery task) modes.
    """

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        """
        Run Trivy scan and extract vulnerability features.

        Uses shared worktree from GitRepoProvider for efficient scanning.
        """
        # Check if Trivy is enabled
        if not settings.TRIVY_ENABLED:
            logger.info("Trivy scanning is disabled")
            return self._get_empty_features()

        try:
            # Get git repo resource with shared worktree
            git_handle = context.get_resource(ResourceNames.GIT_REPO)
            if not git_handle:
                logger.warning("Git repo resource not available for Trivy scan")
                return self._get_empty_features()

            # Use shared worktree from GitRepoProvider
            if not git_handle.has_worktree:
                logger.warning("No shared worktree available for Trivy scan")
                context.add_warning("Trivy scan skipped: no worktree available")
                return self._get_empty_features()

            worktree_path = git_handle.worktree_path
            commit_sha = git_handle.effective_sha

            # Get Trivy client
            trivy_client = context.get_resource("trivy_client")
            if not trivy_client:
                logger.warning("Trivy client resource not available")
                context.add_warning("Trivy scan skipped: client not initialized")
                return self._get_empty_features()

            # Check if should use async mode (large repos)
            if self._should_use_async(context):
                return self._start_async_scan(context, worktree_path, commit_sha)

            # Sync scan - run inline
            return self._run_sync_scan(context, trivy_client, worktree_path, commit_sha)

        except Exception as e:
            logger.error(f"Trivy vulnerability extraction failed: {e}")
            context.add_warning(f"Trivy extraction failed: {e}")
            return self._get_empty_features()

    def _should_use_async(self, context: ExecutionContext) -> bool:
        """Determine if async mode should be used based on repo size."""
        # Use async for large repos (configurable threshold)
        threshold = getattr(settings, "TRIVY_ASYNC_THRESHOLD", 0)
        if threshold <= 0:
            return False  # Async disabled

        # Check file count in worktree
        git_handle = context.get_resource(ResourceNames.GIT_REPO)
        if git_handle and git_handle.has_worktree:
            try:
                file_count = sum(
                    1 for _ in git_handle.worktree_path.rglob("*") if _.is_file()
                )
                return file_count >= threshold
            except Exception:
                pass

        return False

    def _run_sync_scan(
        self, context: ExecutionContext, trivy_client, worktree_path, commit_sha: str
    ) -> Dict[str, Any]:
        """Run Trivy scan synchronously (inline)."""
        start_time = time.time()
        logger.info(
            f"Starting sync Trivy scan on {worktree_path} (commit {commit_sha[:8]})"
        )

        scan_results = trivy_client.scan_filesystem(
            target_path=str(worktree_path),
            scan_types=["vuln", "config", "secret"],
        )

        scan_duration_ms = int((time.time() - start_time) * 1000)

        if "error" in scan_results and scan_results["error"]:
            error_msg = scan_results["error"]
            logger.warning(f"Trivy scan error: {error_msg}")
            context.add_warning(f"Trivy scan encountered error: {error_msg}")
            return self._get_empty_features()

        features = self._format_results(scan_results, scan_duration_ms)

        logger.info(
            f"Trivy scan completed: {features.get('trivy_vuln_total', 0)} vulnerabilities, "
            f"{features.get('trivy_misconfig_total', 0)} misconfigs in {scan_duration_ms}ms"
        )

        return features

    def _start_async_scan(
        self, context: ExecutionContext, worktree_path, commit_sha: str
    ) -> Dict[str, Any]:
        """Start async Trivy scan via Celery task."""
        from app.tasks.trivy import start_trivy_scan

        build = context.build_sample
        build_id = str(build.id)
        build_type = (
            "enrichment" if "Enrichment" in build.__class__.__name__ else "model"
        )

        # Start async scan
        start_trivy_scan.delay(
            build_id=build_id,
            build_type=build_type,
            worktree_path=str(worktree_path),
            commit_sha=commit_sha,
        )

        context.add_warning(
            f"Trivy scan started async for {commit_sha[:8]}, "
            "features will be updated when scan completes"
        )
        logger.info(f"Started async Trivy scan for commit {commit_sha[:8]}")

        return self._get_empty_features()

    def _format_results(
        self, scan_results: Dict[str, Any], scan_duration_ms: int
    ) -> Dict[str, Any]:
        """Format Trivy scan results to feature dictionary."""
        return {
            "trivy_vuln_critical": scan_results.get("vuln_critical", 0),
            "trivy_vuln_high": scan_results.get("vuln_high", 0),
            "trivy_vuln_medium": scan_results.get("vuln_medium", 0),
            "trivy_vuln_low": scan_results.get("vuln_low", 0),
            "trivy_vuln_total": scan_results.get("vuln_total", 0),
            "trivy_misconfig_critical": scan_results.get("misconfig_critical", 0),
            "trivy_misconfig_high": scan_results.get("misconfig_high", 0),
            "trivy_misconfig_medium": scan_results.get("misconfig_medium", 0),
            "trivy_misconfig_low": scan_results.get("misconfig_low", 0),
            "trivy_misconfig_total": scan_results.get("misconfig_total", 0),
            "trivy_secrets_count": scan_results.get("secrets_count", 0),
            "trivy_scan_duration_ms": scan_duration_ms,
            "trivy_packages_scanned": scan_results.get("packages_scanned", 0),
            "trivy_files_scanned": scan_results.get("files_scanned", 0),
            "trivy_has_critical": scan_results.get("has_critical", False),
            "trivy_has_high": scan_results.get("has_high", False),
            "trivy_top_vulnerable_packages": scan_results.get(
                "top_vulnerable_packages", []
            ),
        }

    def _get_empty_features(self) -> Dict[str, Any]:
        """Return dict with all Trivy features set to default values."""
        return {
            "trivy_vuln_critical": 0,
            "trivy_vuln_high": 0,
            "trivy_vuln_medium": 0,
            "trivy_vuln_low": 0,
            "trivy_vuln_total": 0,
            "trivy_misconfig_critical": 0,
            "trivy_misconfig_high": 0,
            "trivy_misconfig_medium": 0,
            "trivy_misconfig_low": 0,
            "trivy_misconfig_total": 0,
            "trivy_secrets_count": 0,
            "trivy_scan_duration_ms": 0,
            "trivy_packages_scanned": 0,
            "trivy_files_scanned": 0,
            "trivy_has_critical": False,
            "trivy_has_high": False,
            "trivy_top_vulnerable_packages": [],
        }

    @classmethod
    def get_empty_features(cls) -> Dict[str, Any]:
        """Return empty/default values for all features this node provides."""
        return {
            "trivy_vuln_critical": 0,
            "trivy_vuln_high": 0,
            "trivy_vuln_medium": 0,
            "trivy_vuln_low": 0,
            "trivy_vuln_total": 0,
            "trivy_misconfig_critical": 0,
            "trivy_misconfig_high": 0,
            "trivy_misconfig_medium": 0,
            "trivy_misconfig_low": 0,
            "trivy_misconfig_total": 0,
            "trivy_secrets_count": 0,
            "trivy_scan_duration_ms": 0,
            "trivy_packages_scanned": 0,
            "trivy_files_scanned": 0,
            "trivy_has_critical": False,
            "trivy_has_high": False,
            "trivy_top_vulnerable_packages": [],
        }
