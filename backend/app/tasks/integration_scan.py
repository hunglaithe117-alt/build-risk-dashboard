"""
Integration Scan Celery Tasks

Tasks for running dataset scans with integration tools.
"""

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bson import ObjectId

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.entities.dataset_scan import DatasetScanStatus
from app.repositories.dataset_scan import DatasetScanRepository
from app.repositories.dataset_scan_result import DatasetScanResultRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.integrations import get_tool, ToolType, ScanMode

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.integration_scan.run_dataset_scan",
    queue="data_processing",
    soft_time_limit=3600,  # 1 hour soft limit
    time_limit=3900,  # 1 hour 5 min hard limit
)
def run_dataset_scan(self, scan_id: str):
    """
    Run a dataset scan job.

    This task:
    1. Loads the scan and its pending results
    2. For each commit, runs the appropriate tool
    3. Updates progress as commits complete
    4. Marks scan as complete when all done
    """
    logger.info(f"Starting dataset scan job: {scan_id}")

    db = get_database()
    scan_repo = DatasetScanRepository(db)
    result_repo = DatasetScanResultRepository(db)
    repo_repo = DatasetRepoConfigRepository(db)

    # Load scan
    scan = scan_repo.find_by_id(scan_id)
    if not scan:
        logger.error(f"Scan not found: {scan_id}")
        return {"status": "error", "error": "Scan not found"}

    # Mark as started
    scan.mark_started()
    scan_repo.update_one(
        scan_id,
        {
            "status": DatasetScanStatus.RUNNING.value,
            "started_at": scan.started_at,
        },
    )

    # Get tool
    tool = get_tool(scan.tool_type)
    if not tool:
        scan_repo.mark_status(
            scan_id, DatasetScanStatus.FAILED, f"Unknown tool: {scan.tool_type}"
        )
        return {"status": "error", "error": f"Unknown tool: {scan.tool_type}"}

    if not tool.is_available():
        scan_repo.mark_status(
            scan_id, DatasetScanStatus.FAILED, f"Tool not available: {scan.tool_type}"
        )
        return {"status": "error", "error": f"Tool not available: {scan.tool_type}"}

    # Load pending results
    results = result_repo.find_pending_by_scan(scan_id)
    logger.info(f"Processing {len(results)} commits for scan {scan_id}")

    completed = 0
    failed = 0
    pending = 0

    for result in results:
        try:
            if tool.scan_mode == ScanMode.SYNC:
                # Trivy: run sync scan
                _run_trivy_scan(result, tool, result_repo, repo_repo)
                completed += 1
            else:
                # SonarQube: start async scan
                _start_sonar_scan(result, tool, result_repo, repo_repo)
                pending += 1

            # Update progress
            scan_repo.update_progress(
                scan_id, scanned=completed, failed=failed, pending=pending
            )

        except Exception as e:
            logger.error(f"Failed to scan commit {result.commit_sha}: {e}")
            result_repo.mark_failed(str(result.id), str(e))
            failed += 1
            scan_repo.update_progress(
                scan_id, scanned=completed, failed=failed, pending=pending
            )

    # Determine final status
    if tool.scan_mode == ScanMode.ASYNC and pending > 0:
        # Async tool - mark as partial, will complete via webhook
        scan_repo.mark_status(scan_id, DatasetScanStatus.PARTIAL)
        logger.info(
            f"Scan {scan_id} partial: {completed} completed, {pending} pending webhook"
        )
        return {
            "status": "partial",
            "completed": completed,
            "pending": pending,
            "failed": failed,
        }
    else:
        # Sync tool or all done
        aggregated = result_repo.get_aggregated_results(scan_id)
        scan_repo.mark_status(
            scan_id,
            DatasetScanStatus.COMPLETED,
            results_summary=aggregated,
        )
        logger.info(f"Scan {scan_id} completed: {completed} scanned, {failed} failed")
        return {
            "status": "completed",
            "completed": completed,
            "failed": failed,
        }


def _run_trivy_scan(
    result,
    tool,
    result_repo: DatasetScanResultRepository,
    repo_repo: DatasetRepoConfigRepository,
):
    """Run Trivy scan on a commit (sync)."""
    from app.integrations.tools.trivy import TrivyTool

    logger.info(
        f"Running Trivy scan on {result.repo_full_name}@{result.commit_sha[:8]}"
    )

    result_repo.mark_scanning(str(result.id))

    # Get or create worktree for the commit
    worktree_path, is_temp_clone = _ensure_worktree(
        str(result.dataset_id), result.repo_full_name, result.commit_sha, repo_repo
    )

    if not worktree_path:
        result_repo.mark_failed(str(result.id), "Failed to checkout commit")
        raise Exception("Failed to checkout commit")

    try:
        # Run scan
        trivy_tool: TrivyTool = tool
        scan_result = trivy_tool.scan(str(worktree_path))

        if scan_result.get("status") == "failed":
            result_repo.mark_failed(
                str(result.id), scan_result.get("error", "Scan failed")
            )
            raise Exception(scan_result.get("error", "Scan failed"))

        # Save results
        metrics = scan_result.get("metrics", {})
        duration_ms = scan_result.get("scan_duration_ms")
        result_repo.mark_completed(str(result.id), metrics, duration_ms)

        logger.info(
            f"Trivy scan completed for {result.commit_sha[:8]}: {metrics.get('vuln_total', 0)} vulnerabilities"
        )

    finally:
        # Cleanup worktree (only if we created a temp clone)
        _cleanup_worktree(worktree_path, is_temp_clone)


def _start_sonar_scan(
    result,
    tool,
    result_repo: DatasetScanResultRepository,
    repo_repo: DatasetRepoConfigRepository,
):
    """Start SonarQube scan on a commit (async)."""
    logger.info(
        f"Starting SonarQube scan on {result.repo_full_name}@{result.commit_sha[:8]}"
    )

    # Generate component key
    repo_name_safe = result.repo_full_name.replace("/", "_")
    component_key = f"{repo_name_safe}_{result.commit_sha[:12]}"

    result_repo.mark_scanning(str(result.id), component_key)

    # Get repo URL
    repo = repo_repo.find_by_dataset_and_full_name(
        str(result.dataset_id), result.repo_full_name
    )
    if not repo:
        result_repo.mark_failed(
            str(result.id),
            f"Repository not found: {result.repo_full_name} for dataset {result.dataset_id}",
        )
        raise Exception(f"Repository not found: {result.repo_full_name}")

    repo_url = f"https://github.com/{result.repo_full_name}.git"

    # Dispatch sonar scan task
    from app.tasks.sonar import start_sonar_scan

    start_sonar_scan.delay(
        build_id=str(result.scan_id),  # Use scan_id as reference
        build_type="dataset_scan",
        repo_url=repo_url,
        commit_sha=result.commit_sha,
        component_key=component_key,
    )

    logger.info(f"SonarQube scan dispatched for {component_key}")


def _ensure_worktree(
    dataset_id: str,
    repo_full_name: str,
    commit_sha: str,
    repo_repo: DatasetRepoConfigRepository,
) -> tuple[Optional[Path], bool]:
    """
    Ensure a git worktree exists for the commit.

    First checks if a shared worktree exists at repo-data/worktrees/{repo_id}/{commit_sha}.
    If not, creates a temporary directory with the repo checked out.

    Returns:
        Tuple of (worktree_path, is_temp_clone)
        - is_temp_clone: True if we created a temp clone that needs cleanup
    """
    import subprocess
    import tempfile

    try:
        # Get repo from DB to check if it exists
        repo = repo_repo.find_by_dataset_and_full_name(dataset_id, repo_full_name)
        if not repo:
            logger.error(
                f"Repository not found in DB: {repo_full_name} for dataset {dataset_id}"
            )
            return None, False

        # Check for existing shared worktree first
        # Path: repo-data/worktrees/{repo_id}/{commit_sha}
        shared_worktree_base = Path("../repo-data/worktrees") / str(repo.id)
        shared_worktree_path = shared_worktree_base / commit_sha

        if shared_worktree_path.exists():
            git_marker = shared_worktree_path / ".git"
            if git_marker.exists():
                logger.info(
                    f"Using existing shared worktree at {shared_worktree_path} "
                    f"for {commit_sha[:8]}"
                )
                return shared_worktree_path, False  # Not a temp clone, don't cleanup

        # No existing worktree found, create a temp clone
        logger.info(
            f"No shared worktree found for {commit_sha[:8]}, creating temp clone"
        )

        repo_url = f"https://github.com/{repo_full_name}.git"

        # Create temp directory for worktree
        worktree_dir = Path(tempfile.mkdtemp(prefix=f"scan_{commit_sha[:8]}_"))

        # Clone the repo at specific commit (shallow clone for speed)
        try:
            # First try shallow clone at specific commit
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    commit_sha,
                    repo_url,
                    str(worktree_dir),
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
        except subprocess.CalledProcessError:
            # If shallow clone fails (commit not a branch/tag), do full clone
            logger.info(f"Shallow clone failed, trying full clone for {commit_sha[:8]}")

            # Clean up failed attempt
            import shutil

            if worktree_dir.exists():
                shutil.rmtree(worktree_dir, ignore_errors=True)
            worktree_dir = Path(tempfile.mkdtemp(prefix=f"scan_{commit_sha[:8]}_"))

            # Full clone
            subprocess.run(
                ["git", "clone", repo_url, str(worktree_dir)],
                capture_output=True,
                text=True,
                timeout=600,
                check=True,
            )

            # Checkout specific commit
            subprocess.run(
                ["git", "checkout", commit_sha],
                cwd=str(worktree_dir),
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )

        logger.info(f"Created temp worktree at {worktree_dir} for {commit_sha[:8]}")
        return worktree_dir, True  # Is a temp clone, needs cleanup

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout cloning {repo_full_name}@{commit_sha}")
        return None, False
    except Exception as e:
        logger.error(
            f"Failed to create worktree for {repo_full_name}@{commit_sha}: {e}"
        )
        return None, False


def _cleanup_worktree(worktree_path: Optional[Path], is_temp: bool):
    """
    Clean up a git worktree.

    Only cleans up if is_temp is True (we created a temp clone).
    Shared worktrees are kept for reuse by other tasks.
    """
    import shutil

    if not is_temp:
        logger.debug(f"Keeping shared worktree: {worktree_path}")
        return

    try:
        if worktree_path and worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)
            logger.debug(f"Cleaned up temp worktree: {worktree_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup worktree {worktree_path}: {e}")
