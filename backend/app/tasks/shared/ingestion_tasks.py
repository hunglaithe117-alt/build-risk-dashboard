"""
Shared Ingestion Tasks - Generic tasks for both model and dataset pipelines.

Features:
- Clone/update git repositories (with installation token support)
- Create git worktrees (with fork commit replay support)
- Download build logs from CI providers

Error Handling (SafeTask pattern):
- TransientError: Network timeout, git timeout → retry with backoff
- PermanentError: Invalid repo URL → mark FAILED
- MissingResourceError: Commit not found, logs expired → mark MISSING_RESOURCE
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.entities.raw_build_run import RawBuildRun
    from app.entities.raw_repository import RawRepository
    from app.services.github.github_client import GitHubClient

import redis

from app.celery_app import celery_app
from app.ci_providers import CIProvider, get_ci_provider, get_provider_config
from app.config import settings
from app.core.redis import RedisLock
from app.paths import (
    get_build_logs_path,
    get_repo_path,
    get_worktrees_path,
)
from app.repositories.base_import_build import get_progressive_updater
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import (
    PipelineTask,
    SafeTask,
    TaskState,
    TransientError,
)
from app.tasks.shared.events import publish_ingestion_build_update

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.shared.ingestion_tasks.clone_repo",
    queue="ingestion",
    soft_time_limit=600,
    time_limit=660,
    max_retries=5,
)
def clone_repo(
    self: SafeTask,
    prev_result: Any = None,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    full_name: str = "",
    correlation_id: str = "",
    pipeline_id: str = "",
    pipeline_type: str = "",  # "model" or "dataset"
) -> Dict[str, Any]:
    """
    Clone or update git repository using SafeTask pattern.

    Error Handling:
    - TransientError: Network timeout, git command failure → retry with backoff
    - Success: Preserves cloned repo for reuse (no cleanup on success)
    """
    from app.entities.model_import_build import ResourceStatus

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[clone][repo={full_name}]"
    repo_path = get_repo_path(github_repo_id)

    # Result template
    result = {
        "resource": "git_history",
        "raw_repo_id": raw_repo_id,
        "github_repo_id": github_repo_id,
        "status": "pending",
        "path": None,
        "correlation_id": correlation_id,
        "error": None,
    }

    def _work(state: TaskState) -> Dict[str, Any]:
        """
        Clone/update work function.

        Phases:
        - START: Mark IN_PROGRESS, acquire lock
        - CLONING: Execute git clone/fetch
        - DONE: Mark COMPLETED, publish WebSocket
        """
        nonlocal result

        # Phase: START → Mark IN_PROGRESS
        if state.phase == "START":
            if pipeline_id and pipeline_type:
                try:
                    updater = get_progressive_updater(
                        db=self.db,
                        pipeline_type=pipeline_type,
                        pipeline_id=pipeline_id,
                        raw_repo_id=raw_repo_id,
                    )
                    updater.update_resource_batch(
                        "git_history", ResourceStatus.IN_PROGRESS
                    )
                except Exception as e:
                    logger.warning(f"{log_ctx} Failed to update IN_PROGRESS: {e}")

            state.phase = "CLONING"

        # Phase: CLONING → Execute git commands
        if state.phase == "CLONING":
            try:
                with RedisLock(
                    f"clone:{github_repo_id}",
                    timeout=700,
                    blocking_timeout=60,
                    redis_client=self.redis,
                ):
                    _execute_git_clone_or_fetch(repo_path, full_name, log_ctx)
            except subprocess.CalledProcessError as e:
                error_msg = (
                    f"Git command failed: {e.stderr.decode() if e.stderr else str(e)}"
                )
                raise TransientError(error_msg) from e
            except subprocess.TimeoutExpired as e:
                raise TransientError(f"Git command timed out: {e}") from e
            except Exception as e:
                # Treat unknown git errors as transient (network issues, etc.)
                raise TransientError(f"Clone failed: {e}") from e

            state.phase = "DONE"

        # Phase: DONE → Mark COMPLETED
        if state.phase == "DONE":
            result.update({"status": "cloned", "path": str(repo_path)})

            if pipeline_id and pipeline_type:
                try:
                    updater = get_progressive_updater(
                        db=self.db,
                        pipeline_type=pipeline_type,
                        pipeline_id=pipeline_id,
                        raw_repo_id=raw_repo_id,
                    )
                    updated = updater.update_resource_batch(
                        "git_history", ResourceStatus.COMPLETED
                    )
                    logger.info(
                        f"{log_ctx} Marked {updated} builds git_history=COMPLETED"
                    )
                except Exception as e:
                    logger.warning(f"{log_ctx} Progressive save failed: {e}")

            if pipeline_id:
                publish_ingestion_build_update(
                    repo_id=pipeline_id,
                    resource="git_history",
                    status="completed",
                    pipeline_type=pipeline_type,
                )

        return result

    def _mark_failed(exc: Exception) -> None:
        """Mark git_history as FAILED in database."""
        error_msg = str(exc)[:500]
        result.update({"status": "failed", "error": error_msg})

        if pipeline_id and pipeline_type:
            try:
                updater = get_progressive_updater(
                    db=self.db,
                    pipeline_type=pipeline_type,
                    pipeline_id=pipeline_id,
                    raw_repo_id=raw_repo_id,
                )
                updater.update_resource_batch(
                    "git_history", ResourceStatus.FAILED, error_msg
                )
            except Exception as e:
                logger.warning(f"{log_ctx} Failed to mark FAILED: {e}")

        if pipeline_id:
            publish_ingestion_build_update(
                repo_id=pipeline_id,
                resource="git_history",
                status="failed",
                pipeline_type=pipeline_type,
            )

    logger.info(f"{log_ctx} Starting clone/update")

    return self.run_safe(
        job_id=f"{pipeline_id}:{raw_repo_id}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=None,  # No cleanup - preserve successful clones for reuse
        fail_on_unknown=False,  # Treat unknown errors as transient (retry)
    )


def _execute_git_clone_or_fetch(repo_path: Path, full_name: str, log_ctx: str) -> None:
    """
    Execute git clone or fetch operation.

    Args:
        repo_path: Path to the bare repository
        full_name: GitHub full name (owner/repo)
        log_ctx: Logging context prefix
    """
    from app.services.model_repository_service import is_org_repo

    use_installation_token = is_org_repo(full_name) and settings.GITHUB_INSTALLATION_ID

    if repo_path.exists():
        logger.info(f"{log_ctx} Updating existing clone")

        if use_installation_token:
            from app.services.github.github_app import get_installation_token

            token = get_installation_token()
            auth_url = f"https://x-access-token:{token}@github.com/{full_name}.git"
            subprocess.run(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=30,
            )

        subprocess.run(
            ["git", "fetch", "--all", "--prune"],
            cwd=str(repo_path),
            check=True,
            capture_output=True,
            timeout=300,
        )
    else:
        logger.info(f"{log_ctx} Cloning to {repo_path}")
        clone_url = f"https://github.com/{full_name}.git"

        if use_installation_token:
            from app.services.github.github_app import get_installation_token

            token = get_installation_token()
            clone_url = f"https://x-access-token:{token}@github.com/{full_name}.git"

        subprocess.run(
            ["git", "clone", "--bare", clone_url, str(repo_path)],
            check=True,
            capture_output=True,
            timeout=600,
        )

    logger.info(f"{log_ctx} Clone/update completed successfully")


@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.shared.ingestion_tasks.create_worktree_chunk",
    queue="ingestion",
    soft_time_limit=600,  # 10 min per chunk (fork replay needs more time)
    time_limit=660,
    max_retries=3,
)
def create_worktree_chunk(
    self: SafeTask,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    commit_shas: Optional[List[str]] = None,
    chunk_index: int = 0,
    total_chunks: int = 1,
    correlation_id: str = "",
    pipeline_id: str = "",
    pipeline_type: str = "",  # "model" or "dataset"
) -> Dict[str, Any]:
    """
    Create worktrees for a chunk of commits using SafeTask pattern.

    Error Handling:
    - TransientError: Network/git issues → retry with backoff
    - MissingResourceError: Commit not found → mark MISSING_RESOURCE (no retry)
    - Success: Preserves worktrees for reuse (no cleanup)

    Returns result with created_commits and failed_commits for progressive save.
    """
    from app.entities.model_import_build import ResourceStatus

    task_id = self.request.id or "unknown"
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = (
        f"{corr_prefix}[worktree][task={task_id}]"
        f"[repo={raw_repo_id}][chunk={chunk_index + 1}/{total_chunks}]"
    )

    sha_list = commit_shas or []
    logger.info(f"{log_ctx} Starting with {len(sha_list)} commits")

    # Result template
    result = {
        "resource": "git_worktree",
        "chunk_index": chunk_index,
        "worktrees_created": 0,
        "worktrees_skipped": 0,
        "worktrees_failed": 0,
        "fork_commits_replayed": 0,
        "correlation_id": correlation_id,
        "error": None,
        "created_commits": [],
        "failed_commits": [],
    }

    if not commit_shas:
        return result

    def _work(state: TaskState) -> Dict[str, Any]:
        """
        Process worktree creation for all commits.

        Phases:
        - START: Mark IN_PROGRESS
        - PROCESSING: Create worktrees for each commit
        - DONE: Progressive save and publish WebSocket
        """
        nonlocal result

        # Phase: START → Mark IN_PROGRESS
        if state.phase == "START":
            if pipeline_id and pipeline_type and commit_shas:
                try:
                    updater = get_progressive_updater(
                        db=self.db,
                        pipeline_type=pipeline_type,
                        pipeline_id=pipeline_id,
                        raw_repo_id=raw_repo_id,
                    )
                    updater.update_resource_by_commits(
                        "git_worktree", commit_shas, ResourceStatus.IN_PROGRESS
                    )
                except Exception as e:
                    logger.warning(f"{log_ctx} Failed to update IN_PROGRESS: {e}")

            state.phase = "PROCESSING"
            state.meta["processed_commits"] = []

        # Phase: PROCESSING → Create worktrees
        if state.phase == "PROCESSING":
            processed = set(state.meta.get("processed_commits", []))
            remaining_shas = [sha for sha in commit_shas if sha not in processed]

            worktrees_created = result["worktrees_created"]
            worktrees_skipped = result["worktrees_skipped"]
            worktrees_failed = result["worktrees_failed"]
            fork_commits_replayed = result["fork_commits_replayed"]
            created_commits = list(result["created_commits"])
            failed_commits = list(result["failed_commits"])

            # Setup repos
            build_run_repo = RawBuildRunRepository(self.db)
            raw_repo_repo = RawRepositoryRepository(self.db)
            raw_repo = raw_repo_repo.find_by_id(raw_repo_id)

            repo_path = get_repo_path(github_repo_id)
            worktrees_dir = get_worktrees_path(github_repo_id)
            worktrees_dir.mkdir(parents=True, exist_ok=True)

            if not repo_path.exists():
                raise TransientError(f"Repo not cloned at {repo_path}")

            # Get GitHub client for fork commit replay
            github_client = None
            try:
                from app.services.github.github_client import get_public_github_client

                github_client = get_public_github_client()
            except Exception as e:
                logger.warning(f"Failed to get GitHub client for fork replay: {e}")

            for sha in remaining_shas:
                worktree_path = worktrees_dir / sha[:12]
                if worktree_path.exists():
                    worktrees_skipped += 1
                    created_commits.append(sha)
                    state.meta["processed_commits"].append(sha)
                    continue

                build_run = build_run_repo.find_by_commit_or_effective_sha(
                    raw_repo_id, sha
                )

                try:
                    res = _process_worktree_commit(
                        sha,
                        github_repo_id,
                        repo_path,
                        worktrees_dir,
                        self.redis,
                        raw_repo,
                        github_client,
                        build_run,
                        build_run_repo,
                    )

                    worktrees_created += res["created"]
                    worktrees_skipped += res["skipped"]
                    worktrees_failed += res["failed"]
                    fork_commits_replayed += res["replayed"]

                    if res["failed"]:
                        failed_commits.append(sha)
                    else:
                        created_commits.append(sha)

                except Exception as e:
                    logger.warning(f"{log_ctx} Error processing commit {sha[:8]}: {e}")
                    worktrees_failed += 1
                    failed_commits.append(sha)

                state.meta["processed_commits"].append(sha)

            result.update(
                {
                    "worktrees_created": worktrees_created,
                    "worktrees_skipped": worktrees_skipped,
                    "worktrees_failed": worktrees_failed,
                    "fork_commits_replayed": fork_commits_replayed,
                    "created_commits": created_commits,
                    "failed_commits": failed_commits,
                }
            )

            logger.info(
                f"{log_ctx} Completed: created={worktrees_created}, "
                f"skipped={worktrees_skipped}, failed={worktrees_failed}"
            )

            state.phase = "DONE"

        # Phase: DONE → Progressive save and publish
        if state.phase == "DONE":
            _save_worktree_progress(
                self.db, pipeline_id, pipeline_type, raw_repo_id, result, log_ctx
            )
            _publish_worktree_update(
                pipeline_id, pipeline_type, chunk_index, total_chunks, result
            )

        return result

    def _mark_failed(exc: Exception) -> None:
        """Mark failed commits in database."""
        error_msg = str(exc)[:500]
        result["error"] = error_msg

        # Mark all unprocessed commits as failed
        if pipeline_id and pipeline_type:
            all_failed = result.get("failed_commits", [])
            # Add unprocessed commits to failed list
            processed = set(result.get("created_commits", []) + all_failed)
            unprocessed = [sha for sha in (commit_shas or []) if sha not in processed]
            all_failed.extend(unprocessed)
            result["failed_commits"] = all_failed

            _save_worktree_progress(
                self.db, pipeline_id, pipeline_type, raw_repo_id, result, log_ctx
            )

    return self.run_safe(
        job_id=f"{pipeline_id}:{raw_repo_id}:chunk{chunk_index}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=None,  # Preserve successful worktrees for reuse
        fail_on_unknown=False,  # Treat unknown errors as transient
    )


def _save_worktree_progress(
    db,
    pipeline_id: str,
    pipeline_type: str,
    raw_repo_id: str,
    result: dict,
    log_ctx: str,
) -> None:
    """Save worktree progress to database."""
    if not pipeline_id or not pipeline_type:
        return

    try:
        from app.entities.model_import_build import ResourceStatus

        updater = get_progressive_updater(
            db=db,
            pipeline_type=pipeline_type,
            pipeline_id=pipeline_id,
            raw_repo_id=raw_repo_id,
        )

        if result.get("created_commits"):
            updated = updater.update_resource_by_commits(
                "git_worktree", result["created_commits"], ResourceStatus.COMPLETED
            )
            logger.info(f"{log_ctx} Marked {updated} builds git_worktree=COMPLETED")

        if result.get("failed_commits"):
            updated = updater.update_resource_by_commits(
                "git_worktree",
                result["failed_commits"],
                ResourceStatus.FAILED,
                result.get("error") or "Worktree creation failed",
            )
            logger.info(f"{log_ctx} Marked {updated} builds git_worktree=FAILED")
    except Exception as e:
        logger.warning(f"{log_ctx} Progressive save failed: {e}")


def _publish_worktree_update(
    pipeline_id: str,
    pipeline_type: str,
    chunk_index: int,
    total_chunks: int,
    result: dict,
) -> None:
    """Publish WebSocket update for worktree progress."""
    is_final_chunk = chunk_index == total_chunks - 1
    if not pipeline_id or not is_final_chunk:
        return

    # Determine overall status
    has_failures = result.get("worktrees_failed", 0) > 0
    has_successes = (
        result.get("worktrees_created", 0) + result.get("worktrees_skipped", 0) > 0
    )

    if has_failures and not has_successes:
        ws_status = "failed"
    elif has_failures and has_successes:
        ws_status = "completed_with_errors"
    else:
        ws_status = "completed"

    publish_ingestion_build_update(
        repo_id=pipeline_id,
        resource="git_worktree",
        status=ws_status,
        builds_affected=result.get("worktrees_created", 0)
        + result.get("worktrees_skipped", 0),
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        pipeline_type=pipeline_type,
        completed_commit_shas=result.get("created_commits") or None,
        failed_commit_shas=result.get("failed_commits") or None,
    )


def _process_worktree_commit(
    sha: str,
    github_repo_id: int,
    repo_path: Path,
    worktrees_dir: Path,
    redis_client: redis.Redis,
    raw_repo: "Optional[RawRepository]",
    github_client: "Optional[GitHubClient]",
    build_run: "Optional[RawBuildRun]",
    build_run_repo: RawBuildRunRepository,
) -> Dict[str, int]:
    """Process a single commit for worktree creation."""
    from app.utils.git import ensure_commit_exists

    result = {"created": 0, "skipped": 0, "failed": 0, "replayed": 0}

    try:
        with RedisLock(
            f"worktree:{github_repo_id}:{sha[:12]}",
            timeout=120,
            blocking_timeout=60,
            redis_client=redis_client,
        ):
            worktree_path = worktrees_dir / sha[:12]
            if worktree_path.exists():
                result["skipped"] = 1
                return result

            # Ensure commit is available (local or replayed from fork)
            commit_sha_to_use = sha
            if not _commit_exists_locally(repo_path, sha):
                if github_client and raw_repo:
                    try:
                        synthetic_sha = ensure_commit_exists(
                            repo_path=repo_path,
                            commit_sha=sha,
                            repo_slug=raw_repo.full_name,
                            github_client=github_client,
                        )
                        if synthetic_sha:
                            if synthetic_sha != sha:
                                if build_run:
                                    build_run_repo.update_effective_sha(
                                        build_run.id, synthetic_sha
                                    )
                                result["replayed"] = 1
                            commit_sha_to_use = synthetic_sha
                        else:
                            # logger.warning(...) passed context?
                            result["skipped"] = 1
                            return result
                    except Exception:
                        result["skipped"] = 1
                        return result
                else:
                    result["skipped"] = 1
                    return result

            # Create worktree
            _create_worktree(repo_path, worktrees_dir, commit_sha_to_use)
            result["created"] = 1
            return result

    except subprocess.CalledProcessError:
        result["failed"] = 1
        return result
    except Exception:
        result["failed"] = 1
        return result


def _commit_exists_locally(repo_path: Any, sha: str) -> bool:
    """Check if commit exists in local repo."""
    res = subprocess.run(
        ["git", "cat-file", "-e", sha],
        cwd=str(repo_path),
        capture_output=True,
        timeout=10,
    )
    return res.returncode == 0


def _create_worktree(repo_path: Any, worktrees_dir: Any, sha: str) -> None:
    """Create a git worktree for a specific commit."""
    worktree_path = worktrees_dir / sha[:12]
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_path), sha],
        cwd=str(repo_path),
        check=True,
        capture_output=True,
        timeout=60,
    )


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.ingestion_tasks.aggregate_logs_results",
    queue="ingestion",
    soft_time_limit=60,
    time_limit=120,
)
def aggregate_logs_results(
    self: PipelineTask,
    chunk_results: List[Dict[str, Any]],  # Results from chord
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    total_chunks: int = 0,
    correlation_id: str = "",
    pipeline_id: str = "",
    pipeline_type: str = "",  # "model" or "dataset"
) -> Dict[str, Any]:
    """
    Chord callback: Aggregate results from parallel log download chunks.

    This task receives results from all chunk tasks after they complete.
    Tracks chunks with errors and publishes final status update.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[logs_aggregate][repo={raw_repo_id}]"

    # Track chunks with errors
    chunks_with_errors = []
    successful_chunks = []

    # Aggregate log IDs from all chunks
    all_failed_log_ids: list[str] = []
    all_expired_log_ids: list[str] = []
    all_downloaded_log_ids: list[str] = []
    all_skipped_log_ids: list[str] = []

    for r in chunk_results:
        # Handle failed task results (exception objects from chord with chord_unlock_on_error)
        if isinstance(r, Exception):
            chunks_with_errors.append(
                {"chunk_index": "?", "error": f"{type(r).__name__}: {str(r)}"}
            )
            logger.warning(
                f"{log_ctx} Chunk failed with exception: {type(r).__name__}: {r}"
            )
            continue
        if not isinstance(r, dict):
            continue
        chunk_idx = r.get("chunk_index", "?")
        if r.get("error"):
            chunks_with_errors.append(
                {"chunk_index": chunk_idx, "error": r.get("error")}
            )
            logger.warning(f"{log_ctx} Chunk {chunk_idx} had error: {r.get('error')}")
        else:
            successful_chunks.append(r)

        # Collect log IDs from each chunk
        all_failed_log_ids.extend(r.get("failed_log_ids", []))
        all_expired_log_ids.extend(r.get("expired_log_ids", []))
        all_downloaded_log_ids.extend(r.get("downloaded_log_ids", []))
        all_skipped_log_ids.extend(r.get("skipped_log_ids", []))

    # Aggregate results from all chunks (including those with partial success)
    total_downloaded = sum(
        r.get("logs_downloaded", 0) for r in chunk_results if isinstance(r, dict)
    )
    total_expired = sum(
        r.get("logs_expired", 0) for r in chunk_results if isinstance(r, dict)
    )
    total_skipped = sum(
        r.get("logs_skipped", 0) for r in chunk_results if isinstance(r, dict)
    )

    # Determine overall status
    if chunks_with_errors:
        status = "completed_with_errors"
        logger.warning(
            f"{log_ctx} Completed with {len(chunks_with_errors)} chunk errors: "
            f"downloaded={total_downloaded}, expired={total_expired}, skipped={total_skipped}"
        )
    else:
        status = "completed"
        logger.info(
            f"{log_ctx} Completed successfully: downloaded={total_downloaded}, "
            f"expired={total_expired}, skipped={total_skipped}"
        )

    result = {
        "resource": "build_logs",
        "status": status,
        "logs_downloaded": total_downloaded,
        "logs_expired": total_expired,
        "logs_skipped": total_skipped,
        "chunks_completed": len(successful_chunks),
        "chunks_with_errors": len(chunks_with_errors),
        "error_details": chunks_with_errors if chunks_with_errors else None,
        "correlation_id": correlation_id,
        "failed_log_ids": all_failed_log_ids,
        "expired_log_ids": all_expired_log_ids,
        "downloaded_log_ids": all_downloaded_log_ids,
        "skipped_log_ids": all_skipped_log_ids,
    }

    # Cleanup Redis session keys to prevent stale stop flags blocking future syncs
    try:
        session_key = f"logs_session:{raw_repo_id}"
        self.redis.delete(f"{session_key}:stop")
        self.redis.delete(f"{session_key}:consecutive")
        self.redis.delete(f"{session_key}:max_expired")
        logger.debug(f"{log_ctx} Cleaned up Redis session keys")
    except Exception as e:
        logger.warning(f"{log_ctx} Failed to cleanup Redis session keys: {e}")

    return result


async def _download_log_for_build(
    build_id: str,
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    redis_client: redis.Redis,
    session_key: str,
    build_run_repo: RawBuildRunRepository,
    ci_instance: Any,
    max_log_size: int,
    max_consecutive: int,
) -> Dict[str, Any]:
    """Helper to download logs for a single build."""
    from app.services.github.exceptions import GithubLogsUnavailableError

    result = {
        "status": "pending",
        "downloaded": 0,
        "expired": 0,
        "skipped": 0,
        "failed_id": None,
        "expired_id": None,
        "downloaded_id": None,
        "skipped_id": None,
    }

    # Check stop flag
    if redis_client.get(f"{session_key}:stop"):
        result["status"] = "stopped"
        return result

    try:
        build_run = build_run_repo.find_by_repo_and_build_id(raw_repo_id, build_id)

        if build_run and build_run.logs_available:
            # Verify log files actually exist on disk
            expected_logs_dir = get_build_logs_path(github_repo_id, build_id)
            if expected_logs_dir.exists() and any(expected_logs_dir.glob("*.log")):
                result["skipped"] = 1
                result["skipped_id"] = build_id
                result["status"] = "skipped"
                return result
            else:
                logger.info(f"Log files missing for {build_id}, re-downloading...")
                build_run_repo.update_one(
                    str(build_run.id),
                    {"logs_available": False, "logs_path": None},
                )

        build_logs_dir = get_build_logs_path(github_repo_id, build_id)
        build_logs_dir.mkdir(parents=True, exist_ok=True)

        fetch_kwargs = {"build_id": f"{full_name}:{build_id}"}
        ci_instance.wait_rate_limit()
        log_files = await ci_instance.fetch_build_logs(**fetch_kwargs)

        if not log_files:
            if build_run:
                build_run_repo.update_one(
                    str(build_run.id),
                    {"logs_available": False, "logs_expired": True},
                )
            result["expired"] = 1
            result["expired_id"] = build_id
            result["status"] = "expired"

            consecutive = redis_client.incr(f"{session_key}:consecutive")
            if consecutive >= max_consecutive:
                redis_client.set(f"{session_key}:stop", 1, ex=3600)
                logger.info(f"Setting stop flag: {consecutive} consecutive expired")
            return result

        # Reset consecutive counter on success
        redis_client.set(f"{session_key}:consecutive", 0)

        saved_files = []
        for log_file in log_files:
            if log_file.size_bytes > max_log_size:
                continue
            log_path = build_logs_dir / f"{log_file.job_id}.log"
            log_path.write_text(log_file.content)
            saved_files.append(str(log_path))

        if saved_files:
            if build_run:
                build_run_repo.update_one(
                    str(build_run.id),
                    {"logs_path": str(build_logs_dir), "logs_available": True},
                )
            result["downloaded"] = 1
            result["downloaded_id"] = build_id
            result["status"] = "downloaded"
        else:
            result["expired"] = 1
            result["expired_id"] = build_id
            result["status"] = "expired"

        return result

    except GithubLogsUnavailableError:
        if build_run:
            build_run_repo.update_one(
                str(build_run.id),
                {"logs_available": False, "logs_expired": True},
            )
        result["expired"] = 1
        result["expired_id"] = build_id
        result["status"] = "expired"

        consecutive = redis_client.incr(f"{session_key}:consecutive")
        if consecutive >= max_consecutive:
            redis_client.set(f"{session_key}:stop", 1, ex=3600)
        return result

    except Exception as e:
        logger.exception(f"Failed to download logs for build {build_id}: {e}")
        result["failed_id"] = build_id
        result["status"] = "failed"
        return result


@celery_app.task(
    bind=True,
    base=SafeTask,
    name="app.tasks.shared.ingestion_tasks.download_logs_chunk",
    queue="ingestion",
    soft_time_limit=600,  # 10 min per chunk
    time_limit=660,
    max_retries=3,
)
def download_logs_chunk(
    self: SafeTask,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    full_name: str = "",
    build_ids: Optional[List[str]] = None,
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    chunk_index: int = 0,
    total_chunks: int = 1,
    correlation_id: str = "",
    pipeline_id: str = "",
    pipeline_type: str = "",  # "model" or "dataset"
) -> Dict[str, Any]:
    """
    Download logs for a chunk of builds using SafeTask pattern.

    Error Handling:
    - TransientError: Network/API issues → retry with backoff
    - MissingResourceError: Logs expired (404) → mark MISSING_RESOURCE (no retry)
    - Success: Preserves downloaded logs for reuse (no cleanup)
    """
    from app.entities.model_import_build import ResourceStatus

    task_id = self.request.id or "unknown"
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = (
        f"{corr_prefix}[logs][task={task_id}]"
        f"[repo={raw_repo_id}][chunk={chunk_index + 1}/{total_chunks}]"
    )

    logger.info(f"{log_ctx} Starting with {len(build_ids or [])} builds")

    # Result template
    result = {
        "resource": "build_logs",
        "chunk_index": chunk_index,
        "logs_downloaded": 0,
        "logs_expired": 0,
        "logs_skipped": 0,
        "correlation_id": correlation_id,
        "error": None,
        "failed_log_ids": [],
        "expired_log_ids": [],
        "downloaded_log_ids": [],
        "skipped_log_ids": [],
    }

    if build_ids is None:
        build_ids = []

    if not build_ids:
        return result

    def _work(state: TaskState) -> Dict[str, Any]:
        """
        Download logs for all builds.

        Phases:
        - START: Mark IN_PROGRESS
        - DOWNLOADING: Process each build
        - DONE: Progressive save
        """
        nonlocal result

        # Phase: START → Mark IN_PROGRESS
        if state.phase == "START":
            if pipeline_id and pipeline_type:
                try:
                    updater = get_progressive_updater(
                        db=self.db,
                        pipeline_type=pipeline_type,
                        pipeline_id=pipeline_id,
                        raw_repo_id=raw_repo_id,
                    )
                    updater.update_resource_by_ci_run_ids(
                        "build_logs", build_ids, ResourceStatus.IN_PROGRESS
                    )
                except Exception as e:
                    logger.warning(f"{log_ctx} Failed to update IN_PROGRESS: {e}")

            state.phase = "DOWNLOADING"
            state.meta["processed_builds"] = []

        # Phase: DOWNLOADING → Download logs
        if state.phase == "DOWNLOADING":
            redis_client = self.redis
            session_key = f"logs_session:{raw_repo_id}"

            # Check early stop flag
            if redis_client.get(f"{session_key}:stop"):
                logger.info(f"{log_ctx} Skipped: stop flag set by another chunk")
                result["skipped"] = True
                result["reason"] = "early_stop"
                state.phase = "DONE"
                return result

            processed = set(state.meta.get("processed_builds", []))
            remaining_builds = [bid for bid in build_ids if bid not in processed]

            build_run_repo = RawBuildRunRepository(self.db)
            ci_provider_enum = CIProvider(ci_provider)
            provider_config = get_provider_config(ci_provider_enum)
            ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

            logs_downloaded = result["logs_downloaded"]
            logs_expired = result["logs_expired"]
            logs_skipped = result["logs_skipped"]
            max_log_size = settings.GIT_MAX_LOG_SIZE_MB * 1024 * 1024
            failed_log_ids = list(result["failed_log_ids"])
            expired_log_ids = list(result["expired_log_ids"])
            downloaded_log_ids = list(result["downloaded_log_ids"])
            skipped_log_ids = list(result["skipped_log_ids"])
            max_consecutive = int(redis_client.get(f"{session_key}:max_expired") or 10)

            async def run_batch():
                nonlocal logs_downloaded, logs_expired, logs_skipped

                for build_id in remaining_builds:
                    res = await _download_log_for_build(
                        build_id,
                        raw_repo_id,
                        github_repo_id,
                        full_name,
                        redis_client,
                        session_key,
                        build_run_repo,
                        ci_instance,
                        max_log_size,
                        max_consecutive,
                    )

                    logs_downloaded += res["downloaded"]
                    logs_expired += res["expired"]
                    logs_skipped += res["skipped"]

                    if res["failed_id"]:
                        failed_log_ids.append(res["failed_id"])
                    if res["expired_id"]:
                        expired_log_ids.append(res["expired_id"])
                    if res["downloaded_id"]:
                        downloaded_log_ids.append(res["downloaded_id"])
                    if res["skipped_id"]:
                        skipped_log_ids.append(res["skipped_id"])

                    state.meta["processed_builds"].append(build_id)

                    if res["status"] == "stopped":
                        break

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_batch())
            finally:
                loop.close()

            result.update(
                {
                    "logs_downloaded": logs_downloaded,
                    "logs_expired": logs_expired,
                    "logs_skipped": logs_skipped,
                    "failed_log_ids": failed_log_ids,
                    "expired_log_ids": expired_log_ids,
                    "downloaded_log_ids": downloaded_log_ids,
                    "skipped_log_ids": skipped_log_ids,
                }
            )

            logger.info(
                f"{log_ctx} Completed: downloaded={logs_downloaded}, "
                f"expired={logs_expired}, skipped={logs_skipped}"
            )

            state.phase = "DONE"

        # Phase: DONE → Progressive save and publish WebSocket
        if state.phase == "DONE":
            _save_logs_progress(
                self.db, pipeline_id, pipeline_type, raw_repo_id, result, log_ctx
            )
            _publish_logs_update(
                pipeline_id, pipeline_type, chunk_index, total_chunks, result
            )

        return result

    def _mark_failed(exc: Exception) -> None:
        """Mark failed logs in database."""
        error_msg = str(exc)[:500]
        result["error"] = error_msg

        if pipeline_id and pipeline_type:
            # Add unprocessed builds to failed list
            all_failed = result.get("failed_log_ids", [])
            processed = set(
                result.get("downloaded_log_ids", [])
                + result.get("skipped_log_ids", [])
                + result.get("expired_log_ids", [])
                + all_failed
            )
            unprocessed = [bid for bid in build_ids if bid not in processed]
            all_failed.extend(unprocessed)
            result["failed_log_ids"] = all_failed

            _save_logs_progress(
                self.db, pipeline_id, pipeline_type, raw_repo_id, result, log_ctx
            )

            # Publish error event
            from app.tasks.shared.events import publish_ingestion_error

            publish_ingestion_error(
                raw_repo_id=raw_repo_id,
                resource="build_logs",
                chunk_index=chunk_index,
                error=error_msg,
                correlation_id=correlation_id,
            )

    return self.run_safe(
        job_id=f"{pipeline_id}:{raw_repo_id}:logs_chunk{chunk_index}",
        work=_work,
        mark_failed_fn=_mark_failed,
        cleanup_fn=None,  # Preserve downloaded logs for reuse
        fail_on_unknown=False,  # Treat unknown errors as transient
    )


def _save_logs_progress(
    db,
    pipeline_id: str,
    pipeline_type: str,
    raw_repo_id: str,
    result: dict,
    log_ctx: str,
) -> None:
    """Save log download progress to database."""
    if not pipeline_id or not pipeline_type:
        return

    try:
        from app.entities.model_import_build import ResourceStatus

        updater = get_progressive_updater(
            db=db,
            pipeline_type=pipeline_type,
            pipeline_id=pipeline_id,
            raw_repo_id=raw_repo_id,
        )

        # Mark downloaded/skipped as COMPLETED
        successful = result.get("downloaded_log_ids", []) + result.get(
            "skipped_log_ids", []
        )
        if successful:
            updated = updater.update_resource_by_ci_run_ids(
                "build_logs", successful, ResourceStatus.COMPLETED
            )
            logger.info(f"{log_ctx} Marked {updated} builds build_logs=COMPLETED")

        # Mark failed/expired as FAILED
        failed = result.get("failed_log_ids", []) + result.get("expired_log_ids", [])
        if failed:
            updated = updater.update_resource_by_ci_run_ids(
                "build_logs",
                failed,
                ResourceStatus.FAILED,
                "Log download failed or expired",
            )
            logger.info(f"{log_ctx} Marked {updated} builds build_logs=FAILED")
    except Exception as e:
        logger.warning(f"{log_ctx} Progressive save failed: {e}")


def _publish_logs_update(
    pipeline_id: str,
    pipeline_type: str,
    chunk_index: int,
    total_chunks: int,
    result: dict,
) -> None:
    """Publish WebSocket update for logs download progress (per chunk)."""
    if not pipeline_id:
        return

    # Determine overall status for this chunk
    completed_ids = result.get("downloaded_log_ids", []) + result.get(
        "skipped_log_ids", []
    )
    failed_ids = result.get("failed_log_ids", []) + result.get("expired_log_ids", [])

    has_failures = len(failed_ids) > 0
    has_successes = len(completed_ids) > 0

    if has_failures and not has_successes:
        ws_status = "failed"
    elif has_failures and has_successes:
        ws_status = "completed_with_errors"
    else:
        ws_status = "completed"

    publish_ingestion_build_update(
        repo_id=pipeline_id,
        resource="build_logs",
        status=ws_status,
        builds_affected=len(completed_ids),
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        pipeline_type=pipeline_type,
        completed_build_ids=completed_ids if completed_ids else None,
        failed_build_ids=failed_ids if failed_ids else None,
    )
