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
from app.repositories.trivy_commit_scan import TrivyCommitScanRepository
from app.tasks.base import SafeTask, TaskState
from app.tasks.shared.events import publish_scan_update

logger = logging.getLogger(__name__)


# TRIVY SCAN TASK - Runs on dedicated trivy_scan queue
@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.trivy.start_trivy_scan_for_version_commit",
    queue="trivy_scan",
    soft_time_limit=600,
    time_limit=900,
    max_retries=3,
)
def start_trivy_scan_for_version_commit(
    self: SafeTask,
    scenario_id: str,
    commit_sha: str,
    repo_full_name: str,
    raw_repo_id: str,
    github_repo_id: int,
    trivy_config: Dict[str, Any],
    selected_metrics: List[str],
    config_file_path: str = "",
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Run Trivy scan for a commit in a training scenario using SafeTask.run_safe() pattern.

    Phases:
    - START: Create scan record, validate worktree
    - SCANNING: Run Trivy CLI scan
    - BACKFILLING: Process metrics and backfill to builds
    - DONE: Return result
    """
    from pathlib import Path

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    trivy_config = trivy_config or {}
    selected_metrics = selected_metrics or []

    db = get_database()
    trivy_scan_repo = TrivyCommitScanRepository(db)

    # Detect pipeline type from scenario_id
    from app.tasks.shared.pipeline_context import PipelineContext

    pipeline_ctx = PipelineContext.detect(db, scenario_id)

    # Pre-validation: Create or get scan record
    scan_record = trivy_scan_repo.create_or_get_for_scenario(
        scenario_id=ObjectId(scenario_id),
        commit_sha=commit_sha,
        repo_full_name=repo_full_name,
        raw_repo_id=ObjectId(raw_repo_id),
        scan_config=trivy_config,
        selected_metrics=selected_metrics,
    )

    def _mark_failed(exc: Exception) -> None:
        """Mark scan as failed and publish error."""
        error_msg = str(exc)
        trivy_scan_repo.mark_failed(scan_record.id, error_msg)
        publish_scan_update(
            scenario_id=scenario_id,
            scan_id=str(scan_record.id),
            commit_sha=commit_sha,
            tool_type="trivy",
            status="failed",
            error=error_msg,
        )
        # Increment scans_failed counter (context-aware for version or scenario)
        try:
            from app.tasks.shared.scan_context_helpers import (
                check_and_mark_scans_completed,
                increment_scan_failed,
            )

            increment_scan_failed(db, scenario_id)
            check_and_mark_scans_completed(db, scenario_id)

            # Context-aware notification (works for both DatasetVersion and MLScenario)
            if pipeline_ctx:
                pipeline_ctx.check_and_notify_completed()
        except Exception as e:
            logger.warning(f"Failed to update scan failure stats: {e}")

    def _cleanup(state: TaskState) -> None:
        """Reset scan status for retry."""
        # No cleanup needed - scan record status is reset by create_or_get on retry
        pass

    def _work(state: TaskState) -> Dict[str, Any]:
        """Trivy scan work function with phases."""
        # Phase: START - Validate worktree
        if state.phase == "START":
            logger.info(
                f"{corr_prefix} Starting Trivy scan for commit {commit_sha[:8]} "
                f"in scenario {scenario_id[:8]}"
            )

            worktree_path = get_worktree_path(github_repo_id, commit_sha)
            if not worktree_path.exists():
                error_msg = (
                    f"Worktree not found for {repo_full_name} @ {commit_sha[:8]}"
                )
                logger.error(error_msg)
                trivy_scan_repo.mark_failed(scan_record.id, error_msg)
                raise ValueError(error_msg)

            state.meta["worktree_path"] = str(worktree_path)

            # Mark as scanning
            trivy_scan_repo.mark_scanning(scan_record.id)
            publish_scan_update(
                scenario_id=scenario_id,
                scan_id=str(scan_record.id),
                commit_sha=commit_sha,
                tool_type="trivy",
                status="scanning",
            )

            state.meta["start_time"] = time.time()
            state.phase = "SCANNING"

        # Phase: SCANNING - Run Trivy CLI
        if state.phase == "SCANNING":
            worktree_path_str = state.meta["worktree_path"]

            trivy_tool = TrivyTool()
            scan_result = trivy_tool.scan(
                target_path=worktree_path_str,
                scan_types=_parse_scan_types(trivy_config),
                config_file_path=Path(config_file_path) if config_file_path else None,
            )

            scan_duration_ms = scan_result.get(
                "scan_duration_ms", int((time.time() - state.meta["start_time"]) * 1000)
            )

            if scan_result.get("status") == "failed":
                error_msg = scan_result.get("error", "Unknown error")
                logger.error(
                    f"{corr_prefix} Trivy scan failed for {commit_sha[:8]}: {error_msg}"
                )
                trivy_scan_repo.mark_failed(scan_record.id, error_msg)
                return {"status": "error", "error": error_msg}

            # Process metrics
            raw_metrics = scan_result.get("metrics", {})
            raw_metrics["scan_duration_ms"] = scan_duration_ms

            state.meta["raw_metrics"] = raw_metrics
            state.meta["scan_duration_ms"] = scan_duration_ms
            state.phase = "BACKFILLING"

        # Phase: BACKFILLING - Backfill to builds
        if state.phase == "BACKFILLING":
            raw_metrics = state.meta["raw_metrics"]
            scan_duration_ms = state.meta["scan_duration_ms"]

            filtered_metrics = _filter_trivy_metrics(raw_metrics, selected_metrics)

            # Context-aware backfill (works for both DatasetVersion and MLScenario)
            updated_count = 0
            if pipeline_ctx:
                updated_count = pipeline_ctx.backfill_scan_metrics_by_commit(
                    commit_sha=commit_sha,
                    scan_features=filtered_metrics,
                    prefix="trivy_",
                )

            trivy_scan_repo.mark_completed(
                scan_id=scan_record.id,
                metrics=filtered_metrics,
                builds_affected=updated_count,
            )

            logger.info(
                f"{corr_prefix} Trivy scan completed for {commit_sha[:8]}: "
                f"{filtered_metrics.get('vuln_total', 0)} vulns, "
                f"backfilled to {updated_count} builds ({scan_duration_ms}ms)"
            )

            publish_scan_update(
                scenario_id=scenario_id,
                scan_id=str(scan_record.id),
                commit_sha=commit_sha,
                tool_type="trivy",
                status="completed",
                metrics=filtered_metrics,
                builds_affected=updated_count,
            )

            # Increment scans_completed counter (context-aware for version or scenario)
            from app.tasks.shared.scan_context_helpers import (
                check_and_mark_scans_completed,
                increment_scan_completed,
            )

            increment_scan_completed(db, scenario_id)
            check_and_mark_scans_completed(db, scenario_id)

            state.meta["result"] = {
                "status": "success",
                "builds_updated": updated_count,
                "vuln_total": filtered_metrics.get("vuln_total", 0),
                "scan_duration_ms": scan_duration_ms,
            }

            # Context-aware notification (works for both DatasetVersion and MLScenario)
            try:
                if pipeline_ctx:
                    pipeline_ctx.check_and_notify_completed()
            except Exception as e:
                logger.warning(
                    f"{corr_prefix} Failed to check completion notification: {e}"
                )

            state.phase = "DONE"

        # Phase: DONE
        return state.meta.get("result", {"status": "completed"})

    return self.run_safe(
        job_id=f"trivy:{scenario_id}:{commit_sha[:8]}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=_cleanup,
        fail_on_unknown=False,  # Unknown errors → retry
    )


def _parse_scan_types(trivy_config: dict) -> List[str]:
    """Parse scan types from config, default to all types for comprehensive scanning."""
    default_types = ["vuln", "misconfig", "secret"]

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
