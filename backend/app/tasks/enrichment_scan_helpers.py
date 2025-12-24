"""
Version-Scoped Scan Dispatch for Enrichment Builds.

Entry point: dispatch_scan_for_commit
- Dispatches Trivy scan to trivy_scan queue
- Dispatches SonarQube scan to sonar_scan queue

Note: Scan record creation is handled by the scan tasks themselves (idempotent).
"""

import logging
from typing import Any, Dict

from app.celery_app import celery_app
from app.core.tracing import TracingContext
from app.repositories.dataset_version import DatasetVersionRepository
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.enrichment_scan_helpers.dispatch_scan_for_commit",
    queue="processing",
    soft_time_limit=60,
    time_limit=120,
)
def dispatch_scan_for_commit(
    self: PipelineTask,
    version_id: str,
    raw_repo_id: str,
    github_repo_id: int,
    commit_sha: str,
    repo_full_name: str,
) -> Dict[str, Any]:
    """
    Dispatch scans for a single commit in a dataset version.

    Creates tracking records and dispatches tasks to dedicated queues.

    Args:
        version_id: DatasetVersion ID
        raw_repo_id: RawRepository MongoDB ID
        github_repo_id: GitHub's internal repository ID for paths
        commit_sha: Commit SHA to scan
        repo_full_name: Repository full name (owner/repo)
    """
    # Get correlation_id from tracing context (set by parent enrichment task)
    correlation_id = TracingContext.get_correlation_id()
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    version_repo = DatasetVersionRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        logger.error(f"{corr_prefix} Version {version_id} not found")
        return {"status": "error", "error": "Version not found"}

    results = {"trivy": None, "sonarqube": None}

    # Dispatch Trivy scan
    trivy_metrics = version.scan_metrics.get("trivy", [])
    if trivy_metrics:
        try:
            trivy_config = version.scan_config.get("trivy", {})

            from app.tasks.trivy import start_trivy_scan_for_version_commit

            start_trivy_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=repo_full_name,
                raw_repo_id=raw_repo_id,
                github_repo_id=github_repo_id,
                trivy_config=trivy_config,
                selected_metrics=trivy_metrics,
                correlation_id=correlation_id,
            )

            results["trivy"] = {"status": "dispatched"}
            logger.info(f"{corr_prefix} Dispatched Trivy scan for commit {commit_sha[:8]}")

        except Exception as exc:
            logger.warning(
                f"{corr_prefix} Failed to dispatch Trivy scan for {commit_sha[:8]}: {exc}"
            )
            results["trivy"] = {"status": "error", "error": str(exc)}

    # Dispatch SonarQube scan
    sonar_metrics = version.scan_metrics.get("sonarqube", [])
    if sonar_metrics:
        try:
            sonar_config = version.scan_config.get("sonarqube", {})

            # Generate component key with version_id prefix for uniqueness
            repo_name_safe = repo_full_name.replace("/", "_")
            version_prefix = version_id[:8]
            component_key = f"{version_prefix}_{repo_name_safe}_{commit_sha[:12]}"

            config_content = _build_sonar_config_content(sonar_config)

            from app.tasks.sonar import start_sonar_scan_for_version_commit

            start_sonar_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=repo_full_name,
                raw_repo_id=raw_repo_id,
                github_repo_id=github_repo_id,
                component_key=component_key,
                config_content=config_content,
                correlation_id=correlation_id,
            )

            results["sonarqube"] = {"status": "dispatched", "component_key": component_key}
            logger.info(f"{corr_prefix} Dispatched SonarQube scan for commit {commit_sha[:8]}")

        except Exception as exc:
            logger.warning(
                f"{corr_prefix} Failed to dispatch SonarQube scan for {commit_sha[:8]}: {exc}"
            )
            results["sonarqube"] = {"status": "error", "error": str(exc)}

    return {
        "status": "dispatched",
        "commit_sha": commit_sha,
        "correlation_id": correlation_id,
        "results": results,
    }


def _build_sonar_config_content(sonar_config: dict) -> str:
    """Build sonar-project.properties content from config dict."""
    config_lines = []

    if sonar_config.get("projectKey"):
        config_lines.append(f"sonar.projectKey={sonar_config['projectKey']}")

    if sonar_config.get("extraProperties"):
        extra_lines = sonar_config["extraProperties"].strip().split("\n")
        config_lines.extend(extra_lines)

    return "\n".join(config_lines) if config_lines else None
