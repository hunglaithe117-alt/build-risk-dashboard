"""
Integration Scan Celery Tasks

Tasks for running dataset scans with integration tools.
"""

import logging
from pathlib import Path
from typing import Optional

from app.celery_app import celery_app
from app.database.mongo import get_database
from app.entities.dataset_scan import DatasetScanStatus
from app.integrations import ScanMode, get_tool
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.dataset_scan import DatasetScanRepository
from app.repositories.dataset_scan_result import DatasetScanResultRepository

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.integration_scan.run_dataset_scan",
    queue="processing",
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
    dataset_repo_config = DatasetRepoConfigRepository(db)

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
        scan_repo.mark_status(scan_id, DatasetScanStatus.FAILED, f"Unknown tool: {scan.tool_type}")
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
                _run_trivy_scan(result, tool, result_repo, dataset_repo_config)
                completed += 1
            else:
                # SonarQube: start async scan
                _start_sonar_scan(result, tool, result_repo, dataset_repo_config)
                pending += 1

            # Update progress
            scan_repo.update_progress(scan_id, scanned=completed, failed=failed, pending=pending)

        except Exception as e:
            logger.error(f"Failed to scan commit {result.commit_sha}: {e}")
            result_repo.mark_failed(str(result.id), str(e))
            failed += 1
            scan_repo.update_progress(scan_id, scanned=completed, failed=failed, pending=pending)

    # Determine final status
    if tool.scan_mode == ScanMode.ASYNC and pending > 0:
        # Async tool - mark as partial, will complete via webhook
        scan_repo.mark_status(scan_id, DatasetScanStatus.PARTIAL)
        logger.info(f"Scan {scan_id} partial: {completed} completed, {pending} pending webhook")
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


@celery_app.task(
    bind=True,
    name="app.tasks.integration_scan.retry_scan_result",
    queue="processing",
    soft_time_limit=600,  # 10 min soft limit
    time_limit=660,  # 11 min hard limit
)
def retry_scan_result(self, result_id: str, scan_id: str):
    """
    Retry a single failed scan result.

    Uses config hierarchy: result.override_config > scan.scan_config > default
    """
    logger.info(f"Retrying scan result: {result_id}")

    db = get_database()
    scan_repo = DatasetScanRepository(db)
    result_repo = DatasetScanResultRepository(db)
    dataset_repo_config = DatasetRepoConfigRepository(db)

    # Load result
    result = result_repo.find_by_id(result_id)
    if not result:
        logger.error(f"Result not found: {result_id}")
        return {"status": "error", "error": "Result not found"}

    # Load scan
    scan = scan_repo.find_by_id(scan_id)
    if not scan:
        logger.error(f"Scan not found: {scan_id}")
        return {"status": "error", "error": "Scan not found"}

    # Get tool
    tool = get_tool(scan.tool_type)
    if not tool or not tool.is_available():
        result_repo.mark_failed(result_id, f"Tool not available: {scan.tool_type}")
        return {"status": "error", "error": f"Tool not available: {scan.tool_type}"}

    # Get effective config: override_config > scan_config > None (default)
    effective_config = result.override_config or scan.scan_config

    try:
        if tool.scan_mode == ScanMode.SYNC:
            # Trivy: run sync scan with config
            _run_trivy_scan(result, tool, result_repo, dataset_repo_config, effective_config)
        else:
            # SonarQube: start async scan with config
            _start_sonar_scan(result, tool, result_repo, dataset_repo_config, effective_config)

        # Check scan completion after single result
        from app.services.dataset_scan_service import DatasetScanService

        service = DatasetScanService(db)
        service._check_scan_completion(scan_id)

        logger.info(f"Retry completed for result {result_id}")
        return {"status": "success", "result_id": result_id}

    except Exception as e:
        logger.error(f"Retry failed for result {result_id}: {e}")
        result_repo.mark_failed(result_id, str(e))
        return {"status": "error", "error": str(e)}


def _run_trivy_scan(
    result,
    tool,
    result_repo: DatasetScanResultRepository,
    dataset_repo_config: DatasetRepoConfigRepository,
    config_content: Optional[str] = None,
):
    """Run Trivy scan on a commit (sync)."""
    from app.integrations.tools.trivy import TrivyTool

    logger.info(f"Running Trivy scan on {result.repo_full_name}@{result.commit_sha[:8]}")

    result_repo.mark_scanning(str(result.id))

    # Use effective_sha for worktree if available (for fork commits)
    # Otherwise use commit_sha
    checkout_sha = result.effective_sha or result.commit_sha

    # Get or create worktree for the commit
    worktree_path, is_temp_clone = _ensure_worktree(
        str(result.dataset_id), result.repo_full_name, checkout_sha, dataset_repo_config
    )

    if not worktree_path:
        result_repo.mark_failed(str(result.id), "Failed to checkout commit")
        raise Exception("Failed to checkout commit")

    try:
        # Run scan with optional config
        trivy_tool: TrivyTool = tool
        scan_result = trivy_tool.scan(str(worktree_path), config_content=config_content)

        if scan_result.get("status") == "failed":
            result_repo.mark_failed(str(result.id), scan_result.get("error", "Scan failed"))
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
    dataset_repo_config: DatasetRepoConfigRepository,
    config_content: Optional[str] = None,
):
    """Start SonarQube scan on a commit (async)."""
    logger.info(f"Starting SonarQube scan on {result.repo_full_name}@{result.commit_sha[:8]}")

    # Generate component key using original commit_sha (for result identification)
    repo_name_safe = result.repo_full_name.replace("/", "_")
    component_key = f"{repo_name_safe}_{result.commit_sha[:12]}"

    result_repo.mark_scanning(str(result.id), component_key)

    # Get repo URL
    repo = dataset_repo_config.find_by_dataset_and_full_name(
        str(result.dataset_id), result.repo_full_name
    )
    if not repo:
        result_repo.mark_failed(
            str(result.id),
            f"Repository not found: {result.repo_full_name} for dataset {result.dataset_id}",
        )
        raise Exception(f"Repository not found: {result.repo_full_name}")

    repo_url = f"https://github.com/{result.repo_full_name}.git"

    # Use effective_sha for checkout if available (for fork commits)
    checkout_sha = result.effective_sha or result.commit_sha

    # Get raw_repo_id for shared worktree
    raw_repo_id = str(repo.raw_repo_id) if repo.raw_repo_id else str(repo.id)

    # Dispatch sonar scan task with optional config
    from app.tasks.sonar import start_sonar_scan

    start_sonar_scan.delay(
        build_id=str(result.scan_id),  # Use scan_id as reference
        build_type="dataset_scan",
        repo_url=repo_url,
        commit_sha=checkout_sha,  # Use effective_sha for checkout
        component_key=component_key,
        config_content=config_content,
        raw_repo_id=raw_repo_id,
        full_name=result.repo_full_name,
    )

    logger.info(f"SonarQube scan dispatched for {component_key}")


def _clone_bare_repo(raw_repo_id: str, full_name: str) -> None:
    """
    Clone a repository as bare for worktree creation.

    Uses installation token for org repos.
    Raises exception on failure.
    """
    import subprocess

    from app.config import settings
    from app.core.redis import RedisLock
    from app.paths import REPOS_DIR

    repo_path = REPOS_DIR / raw_repo_id

    with RedisLock(f"clone:{raw_repo_id}", timeout=700, blocking_timeout=60):
        # Double-check after acquiring lock
        if repo_path.exists():
            logger.info(f"Repo already cloned by another process: {repo_path}")
            return

        # Check if org repo for installation token
        from app.services.repository_service import is_org_repo

        clone_url = f"https://github.com/{full_name}.git"

        if is_org_repo(full_name) and settings.GITHUB_INSTALLATION_ID:
            from app.services.github.github_app import get_installation_token

            token = get_installation_token()
            clone_url = f"https://x-access-token:{token}@github.com/{full_name}.git"

        logger.info(f"Cloning {full_name} to {repo_path}")
        subprocess.run(
            ["git", "clone", "--bare", clone_url, str(repo_path)],
            check=True,
            capture_output=True,
            timeout=600,
        )
        logger.info(f"Successfully cloned {full_name}")


def _ensure_worktree(
    dataset_id: str,
    repo_full_name: str,
    commit_sha: str,
    dataset_repo_config: DatasetRepoConfigRepository,
) -> tuple[Optional[Path], bool]:
    """
    Ensure a git worktree exists for the commit.

    Uses shared worktrees from WORKTREES_DIR/{raw_repo_id}/{commit_sha[:12]}.
    If worktree doesn't exist, creates it from bare repo in REPOS_DIR.
    Uses RedisLock to prevent race conditions with ingestion_tasks.

    Returns:
        Tuple of (worktree_path, is_temp_clone)
        - is_temp_clone: Always False for shared worktrees (no cleanup needed)
    """
    import subprocess

    from app.core.redis import RedisLock
    from app.paths import REPOS_DIR, WORKTREES_DIR

    try:
        # Get repo from DB to get raw_repo_id
        repo = dataset_repo_config.find_by_dataset_and_full_name(dataset_id, repo_full_name)
        if not repo:
            logger.error(f"Repository not found in DB: {repo_full_name} for dataset {dataset_id}")
            return None, False

        raw_repo_id = str(repo.raw_repo_id) if repo.raw_repo_id else str(repo.id)

        # Path: WORKTREES_DIR/{raw_repo_id}/{commit_sha[:12]}
        worktrees_dir = WORKTREES_DIR / raw_repo_id
        worktree_path = worktrees_dir / commit_sha[:12]

        # Check for existing shared worktree (quick check without lock)
        if worktree_path.exists():
            git_marker = worktree_path / ".git"
            if git_marker.exists():
                logger.info(
                    f"Using existing shared worktree at {worktree_path} " f"for {commit_sha[:8]}"
                )
                return worktree_path, False

        # Lock to prevent race condition with ingestion_tasks
        with RedisLock(
            f"worktree:{raw_repo_id}:{commit_sha[:12]}",
            timeout=120,
            blocking_timeout=60,
        ):
            # Double-check after acquiring lock
            if worktree_path.exists():
                git_marker = worktree_path / ".git"
                if git_marker.exists():
                    logger.info(f"Worktree created by another process: {worktree_path}")
                    return worktree_path, False

            # Check if bare repo exists, clone if not
            repo_path = REPOS_DIR / raw_repo_id
            if not repo_path.exists():
                logger.info(f"Bare repo not found, cloning {repo_full_name}...")
                try:
                    _clone_bare_repo(raw_repo_id, repo_full_name)
                except Exception as e:
                    logger.error(f"Failed to clone repo {repo_full_name}: {e}")
                    return None, False

            # Verify commit exists in bare repo
            result = subprocess.run(
                ["git", "cat-file", "-e", commit_sha],
                cwd=str(repo_path),
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(
                    f"Commit {commit_sha[:8]} not found in repo {raw_repo_id}. "
                    f"May need to run clone_repo task first or commit is from fork."
                )
                return None, False

            # Create worktree from bare repo
            worktrees_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), commit_sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=60,
            )

            logger.info(f"Created shared worktree at {worktree_path} for {commit_sha[:8]}")
            return worktree_path, False  # Shared worktree, no cleanup needed

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create worktree for {commit_sha[:8]}: {e}")
        return None, False
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout creating worktree for {repo_full_name}@{commit_sha}")
        return None, False
    except Exception as e:
        logger.error(f"Failed to create worktree for {repo_full_name}@{commit_sha}: {e}")
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
