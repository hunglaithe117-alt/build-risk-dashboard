"""
Version-Scoped Scan Dispatch for Enrichment Builds.

Entry point: dispatch_scan_for_commit
- Creates scan records for tracking
- Dispatches Trivy scan to trivy_scan queue
- Dispatches SonarQube scan to sonar_scan queue
"""

import logging
from typing import Any, Dict

from bson import ObjectId

from app.celery_app import celery_app
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.sonar_commit_scan import SonarCommitScanRepository
from app.repositories.trivy_commit_scan import TrivyCommitScanRepository
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.enrichment_scan_helpers.dispatch_scan_for_commit",
    queue="processing",
)
def dispatch_scan_for_commit(
    self: PipelineTask,
    version_id: str,
    raw_repo_id: str,
    commit_sha: str,
    repo_full_name: str,
) -> Dict[str, Any]:
    """
    Dispatch scans for a single commit in a dataset version.

    Creates tracking records and dispatches tasks to dedicated queues.

    Args:
        version_id: DatasetVersion ID
        raw_repo_id: RawRepository ID (used to derive worktree path)
        commit_sha: Commit SHA to scan
        repo_full_name: Repository full name (owner/repo)
    """
    version_repo = DatasetVersionRepository(self.db)
    trivy_scan_repo = TrivyCommitScanRepository(self.db)
    sonar_scan_repo = SonarCommitScanRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        logger.error(f"Version {version_id} not found")
        return {"status": "error", "error": "Version not found"}

    results = {"trivy": None, "sonarqube": None}

    # ---------------------------------------------------------------------
    # Dispatch Trivy scan
    # ---------------------------------------------------------------------
    trivy_metrics = version.scan_metrics.get("trivy", [])
    if trivy_metrics:
        try:
            trivy_config = version.scan_config.get("trivy", {})

            # Create tracking record (stores raw_repo_id for retry)
            trivy_scan_repo.create_or_get(
                version_id=ObjectId(version_id),
                commit_sha=commit_sha,
                repo_full_name=repo_full_name,
                raw_repo_id=ObjectId(raw_repo_id),
                scan_config=trivy_config,
                selected_metrics=trivy_metrics,
            )

            # Dispatch to queue
            from app.tasks.trivy import start_trivy_scan_for_version_commit

            start_trivy_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=repo_full_name,
                raw_repo_id=raw_repo_id,
                trivy_config=trivy_config,
                selected_metrics=trivy_metrics,
            )

            results["trivy"] = {"status": "dispatched"}
            logger.info(f"Dispatched Trivy scan for commit {commit_sha[:8]}")

        except Exception as exc:
            logger.warning(f"Failed to dispatch Trivy scan for {commit_sha[:8]}: {exc}")
            results["trivy"] = {"status": "error", "error": str(exc)}

    # ---------------------------------------------------------------------
    # Dispatch SonarQube scan
    # ---------------------------------------------------------------------
    sonar_metrics = version.scan_metrics.get("sonarqube", [])
    if sonar_metrics:
        try:
            sonar_config = version.scan_config.get("sonarqube", {})

            # Generate component key with version_id prefix for uniqueness
            repo_name_safe = repo_full_name.replace("/", "_")
            version_prefix = version_id[:8]
            component_key = f"{version_prefix}_{repo_name_safe}_{commit_sha[:12]}"

            # Create tracking record (stores raw_repo_id for retry)
            sonar_scan_repo.create_or_get(
                version_id=ObjectId(version_id),
                commit_sha=commit_sha,
                repo_full_name=repo_full_name,
                raw_repo_id=ObjectId(raw_repo_id),
                component_key=component_key,
                scan_config=sonar_config,
            )

            # Build config content
            config_content = _build_sonar_config_content(sonar_config)

            # Dispatch to queue
            from app.tasks.sonar import start_sonar_scan_for_version_commit

            start_sonar_scan_for_version_commit.delay(
                version_id=version_id,
                commit_sha=commit_sha,
                repo_full_name=repo_full_name,
                raw_repo_id=raw_repo_id,
                component_key=component_key,
                config_content=config_content,
            )

            results["sonarqube"] = {"status": "dispatched", "component_key": component_key}
            logger.info(f"Dispatched SonarQube scan for commit {commit_sha[:8]}")

        except Exception as exc:
            logger.warning(f"Failed to dispatch SonarQube scan for {commit_sha[:8]}: {exc}")
            results["sonarqube"] = {"status": "error", "error": str(exc)}

    return {
        "status": "dispatched",
        "commit_sha": commit_sha,
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
