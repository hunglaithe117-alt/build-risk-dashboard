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
from app.repositories.sonar_commit_scan import SonarCommitScanRepository
from app.repositories.training_scenario import TrainingScenarioRepository
from app.tasks.base import PipelineTask, SafeTask, TaskState
from app.tasks.shared.events import publish_scan_update

logger = logging.getLogger(__name__)


# SCAN TASK - Runs on dedicated sonar_scan queue
@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.sonar.start_sonar_scan_for_version_commit",
    queue="sonar_scan",
    soft_time_limit=1800,
    time_limit=2100,
    max_retries=3,
)
def start_sonar_scan_for_version_commit(
    self: SafeTask,
    scenario_id: str,
    commit_sha: str,
    repo_full_name: str,
    raw_repo_id: str,
    github_repo_id: int,
    component_key: str,
    config_file_path: str = "",
    correlation_id: str = "",
) -> dict:
    """
    Start SonarQube scan for a commit in training scenario using SafeTask.run_safe() pattern.

    Phases:
    - START: Create scan record, validate worktree
    - SCANNING: Run sonar-scanner CLI (async - webhook handles completion)
    - DONE: Return status

    Note: Results are handled by export_metrics_from_webhook via SonarQube webhook.
    """
    from pathlib import Path

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    db = get_database()
    scan_repo = SonarCommitScanRepository(db)

    # Pre-validation: Create or get scan record
    scan_record = scan_repo.create_or_get_for_scenario(
        scenario_id=ObjectId(scenario_id),
        commit_sha=commit_sha,
        repo_full_name=repo_full_name,
        raw_repo_id=ObjectId(raw_repo_id),
        component_key=component_key,
    )

    # Check if already scanning (idempotent)
    if scan_record.status.value == "scanning":
        logger.info(f"{corr_prefix} Scan already in progress for {component_key}")
        return {"status": "already_scanning", "component_key": component_key}

    def _mark_failed(exc: Exception) -> None:
        """Mark scan as failed and publish error."""
        error_msg = str(exc)
        scan_repo.mark_failed(scan_record.id, error_msg)
        publish_scan_update(
            scenario_id=scenario_id,
            scan_id=str(scan_record.id),
            commit_sha=commit_sha,
            tool_type="sonarqube",
            status="failed",
            error=error_msg,
        )

    def _cleanup(state: TaskState) -> None:
        """Reset scan status for retry."""
        # No cleanup needed - scan record status is reset by create_or_get on retry
        pass

    def _work(state: TaskState) -> dict:
        """SonarQube scan work function with phases."""
        # Phase: START - Validate worktree
        if state.phase == "START":
            logger.info(
                f"{corr_prefix} Starting SonarQube scan for {commit_sha[:8]} "
                f"in scenario {scenario_id[:8]}"
            )

            worktree_path = get_worktree_path(github_repo_id, commit_sha)
            if not worktree_path.exists():
                error_msg = (
                    f"Worktree not found for {repo_full_name} @ {commit_sha[:8]}"
                )
                logger.error(error_msg)
                scan_repo.mark_failed(scan_record.id, error_msg)
                raise ValueError(error_msg)

            state.meta["worktree_path"] = str(worktree_path)

            # Mark as scanning
            scan_repo.mark_scanning(scan_record.id)
            publish_scan_update(
                scenario_id=scenario_id,
                scan_id=str(scan_record.id),
                commit_sha=commit_sha,
                tool_type="sonarqube",
                status="scanning",
            )

            state.phase = "SCANNING"

        # Phase: SCANNING - Run sonar-scanner CLI
        if state.phase == "SCANNING":
            worktree_path_str = state.meta["worktree_path"]

            project_key = component_key.rsplit("_", 1)[0]
            sonar_tool = SonarQubeTool(
                project_key=project_key, github_repo_id=github_repo_id
            )
            sonar_tool.scan_commit(
                commit_sha=commit_sha,
                full_name=repo_full_name,
                config_file_path=Path(config_file_path) if config_file_path else None,
                shared_worktree_path=worktree_path_str,
                component_key=component_key,
            )

            logger.info(
                f"{corr_prefix} SonarQube scan initiated for {component_key}, waiting for webhook"
            )

            state.meta["result"] = {
                "status": "scanning",
                "component_key": component_key,
            }
            state.phase = "DONE"

        # Phase: DONE
        return state.meta.get("result", {"status": "completed"})

    return self.run_safe(
        job_id=f"sonar:{scenario_id}:{commit_sha[:8]}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=_cleanup,
        fail_on_unknown=False,  # Unknown errors → retry
    )


# WEBHOOK HANDLER - Processes results when SonarQube analysis completes
# Note: Stays as PipelineTask since it's a quick webhook handler
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.sonar.export_metrics_from_webhook",
    queue="dataset_processing",
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

    Fetches metrics, filters by scenario config, and backfills to builds.

    Args:
        component_key: SonarQube component/project key
        analysis_status: Status from webhook ("SUCCESS", "FAILED", etc.)
    """
    logger.info(
        f"Processing SonarQube webhook for {component_key}, status={analysis_status}"
    )

    db = get_database()
    scan_repo = SonarCommitScanRepository(db)
    scenario_repo = TrainingScenarioRepository(db)

    # Find scan record
    scan_record = scan_repo.find_by_component_key(component_key)
    if not scan_record:
        logger.warning(f"No scan record found for {component_key}")
        return {"status": "no_scan_record", "component_key": component_key}

    scenario_id = scan_record.scenario_id
    if not scenario_id:
        logger.error(f"Scan record {scan_record.id} has no scenario_id")
        return {"status": "invalid_record", "component_key": component_key}

    scenario_id_str = str(scenario_id)

    # Detect pipeline type for context-aware operations
    from app.tasks.shared.pipeline_context import PipelineContext

    pipeline_ctx = PipelineContext.detect(db, scenario_id_str)

    try:
        # Handle failed analysis
        if analysis_status != "SUCCESS":
            error_msg = f"Analysis failed: {analysis_status}"
            scan_repo.mark_failed(scan_record.id, error_msg)

            # Publish failed status
            publish_scan_update(
                scenario_id=scenario_id_str,
                scan_id=str(scan_record.id),
                commit_sha=scan_record.commit_sha,
                tool_type="sonarqube",
                status="failed",
                error=error_msg,
            )

            # Increment scans_failed (context-aware for version or scenario)
            from app.tasks.shared.scan_context_helpers import (
                check_and_mark_scans_completed,
                increment_scan_failed,
            )

            increment_scan_failed(db, scenario_id_str)
            check_and_mark_scans_completed(db, scenario_id_str)

            # Context-aware notification (works for both DatasetVersion and MLScenario)
            try:
                if pipeline_ctx:
                    pipeline_ctx.check_and_notify_completed()
            except Exception as e:
                logger.warning(f"Failed to check completion notification: {e}")

            return {"status": "failed", "component_key": component_key}

        # Get scenario to determine which metrics to fetch
        scenario = scenario_repo.find_by_id(scenario_id_str)
        if not scenario:
            logger.error(f"Scenario {scenario_id_str} not found")
            scan_repo.mark_failed(scan_record.id, "Scenario not found")
            return {"status": "scenario_not_found", "component_key": component_key}

        # Get user's selected metrics (only fetch these from SonarQube API)
        # Check both feature_config.scan_metrics (schema) and root scan_metrics (legacy) if needed
        scan_metrics_config = getattr(scenario.feature_config, "scan_metrics", {})
        if not scan_metrics_config and hasattr(scenario, "scan_metrics"):
            scan_metrics_config = scenario.scan_metrics

        selected_metrics = scan_metrics_config.get("sonarqube", [])

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

        # Context-aware backfill (works for both DatasetVersion and MLScenario)
        updated_count = 0
        if pipeline_ctx:
            updated_count = pipeline_ctx.backfill_scan_metrics_by_commit(
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
            scenario_id=scenario_id_str,
            scan_id=str(scan_record.id),
            commit_sha=scan_record.commit_sha,
            tool_type="sonarqube",
            status="completed",
            metrics=metrics,
            builds_affected=updated_count,
        )

        # Increment scans_completed (context-aware for version or scenario)
        from app.tasks.shared.scan_context_helpers import (
            check_and_mark_scans_completed,
            increment_scan_completed,
        )

        increment_scan_completed(db, scenario_id_str)
        check_and_mark_scans_completed(db, scenario_id_str)

        # Context-aware notification (works for both DatasetVersion and MLScenario)
        try:
            if pipeline_ctx:
                pipeline_ctx.check_and_notify_completed()
        except Exception as e:
            logger.warning(f"Failed to check completion notification: {e}")

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
            scenario_id=scenario_id_str,
            scan_id=str(scan_record.id),
            commit_sha=scan_record.commit_sha,
            tool_type="sonarqube",
            status="failed",
            error=str(exc),
        )
        raise
