"""
Shared Ingestion Tasks - Generic tasks for both model and dataset pipelines.

Features:
- Clone/update git repositories (with installation token support)
- Create git worktrees (with fork commit replay support)
- Download build logs from CI providers
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.entities.raw_build_run import RawBuildRun
    from app.entities.raw_repository import RawRepository
    from app.services.github.github_client import GitHubClient

import redis
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.ci_providers import CIProvider, get_ci_provider, get_provider_config
from app.config import settings
from app.core.redis import RedisLock
from app.paths import (
    get_build_logs_path,
    get_repo_path,
    get_worktrees_path,
)
from app.repositories.model_import_build import ModelImportBuildRepository, ResourceStatus
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)


def save_ingestion_result(
    redis_client: redis.Redis, correlation_id: str, result: Dict[str, Any]
) -> None:
    """
    Save ingestion task result to Redis for final aggregation.

    This prevents data loss in Celery chains where intermediate results
    might be dropped.
    """
    if not correlation_id:
        return

    try:
        key = f"ingestion:results:{correlation_id}"
        # Push to list
        redis_client.rpush(key, json.dumps(result))
        # Set expiry (1 hour)
        redis_client.expire(key, 3600)
    except Exception as e:
        logger.error(f"Failed to save ingestion result to Redis: {e}")


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.clone_repo",
    queue="ingestion",
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
)
def clone_repo(
    self: PipelineTask,
    prev_result: Any = None,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    full_name: str = "",
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Clone or update git repository.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[clone][repo={full_name}]"

    logger.info(f"{log_ctx} Starting clone/update")

    # Initialize result with defaults
    result = {
        "resource": "git_history",
        "raw_repo_id": raw_repo_id,
        "github_repo_id": github_repo_id,
        "status": "pending",
        "path": None,
        "correlation_id": correlation_id,
        "error": None,
    }

    repo_path = get_repo_path(github_repo_id)

    try:
        with RedisLock(
            f"clone:{github_repo_id}",
            timeout=700,
            blocking_timeout=60,
            redis_client=self.redis,
        ):
            # Update status to IN_PROGRESS
            if raw_repo_id:
                try:
                    model_config_repo = ModelRepoConfigRepository(self.db)
                    import_build_repo = ModelImportBuildRepository(self.db)

                    # Find all configs using this raw repo
                    configs = model_config_repo.find_by_raw_repo(raw_repo_id)
                    for config in configs:
                        import_build_repo.update_resource_status_batch(
                            str(config.id),
                            "git_history",
                            ResourceStatus.IN_PROGRESS,
                        )
                except Exception as e:
                    logger.warning(f"{log_ctx} Failed to update status to IN_PROGRESS: {e}")

            # Check if this repo belongs to the configured organization
            from app.services.model_repository_service import is_org_repo

            use_installation_token = is_org_repo(full_name) and settings.GITHUB_INSTALLATION_ID

            if repo_path.exists():
                logger.info(f"{log_ctx} Updating existing clone")

                # For org repos, update remote URL with fresh token before fetching
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

                # For org repos, use installation token
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

            result.update(
                {
                    "status": "cloned",
                    "path": str(repo_path),
                }
            )

            # No need to chain previous results, we use Redis for aggregation
            save_ingestion_result(self.redis, correlation_id, result)
            return result

    except SoftTimeLimitExceeded:
        # Task exceeded time limit - return result to continue pipeline
        logger.error(f"{log_ctx} TIMEOUT! Task exceeded soft time limit")
        result.update(
            {
                "status": "timeout",
                "error": "Clone task exceeded time limit",
            }
        )
        # No need to chain previous results
        save_ingestion_result(self.redis, correlation_id, result)
        return result

    except (subprocess.CalledProcessError, TimeoutError, Exception) as e:
        # Check if we have retries left
        retries_left = self.max_retries - self.request.retries

        if retries_left > 0:
            # Still have retries - raise to trigger retry
            logger.warning(
                f"{log_ctx} Clone failed, will retry in 60s " f"({retries_left} retries left): {e}"
            )
            raise self.retry(exc=e, countdown=60) from e
        else:
            # No retries left - log error and return result to continue chain
            error_msg = str(e)
            if isinstance(e, subprocess.CalledProcessError):
                error_msg = f"Git command failed: {e.stderr}"
            logger.error(
                f"{log_ctx} Clone failed after {self.max_retries} retries, "
                f"continuing chain: {error_msg}"
            )
            result.update(
                {
                    "status": "failed",
                    "error": error_msg,
                }
            )

            return result


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.create_worktree_chunk",
    queue="ingestion",
    soft_time_limit=600,  # 10 min per chunk (fork replay needs more time)
    time_limit=660,
    max_retries=2,  # Will retry up to 2 times before giving up gracefully
)
def create_worktree_chunk(
    self: PipelineTask,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    commit_shas: Optional[List[str]] = None,
    chunk_index: int = 0,
    total_chunks: int = 1,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Worker: Create worktrees for a chunk of commits.

    Runs as part of a chain, each chunk executes sequentially.
    This task NEVER raises exceptions to ensure the chain continues.
    All errors are logged and counted in the result.
    """
    task_id = self.request.id or "unknown"
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = (
        f"{corr_prefix}[worktree][task={task_id}]"
        f"[repo={raw_repo_id}][chunk={chunk_index + 1}/{total_chunks}]"
    )

    # Log all commit SHAs for debugging
    sha_list = commit_shas or []
    logger.info(
        f"{log_ctx} Starting with {len(sha_list)} commits: " f"{[sha[:8] for sha in sha_list]}"
    )

    # Update status to IN_PROGRESS for these commits
    if raw_repo_id and commit_shas:
        try:
            model_config_repo = ModelRepoConfigRepository(self.db)
            import_build_repo = ModelImportBuildRepository(self.db)
            configs = model_config_repo.find_by_raw_repo(raw_repo_id)
            for config in configs:
                import_build_repo.update_resource_by_commits(
                    str(config.id),
                    "git_worktree",
                    commit_shas,
                    ResourceStatus.IN_PROGRESS,
                )
        except Exception as e:
            logger.warning(f"{log_ctx} Failed to verify IN_PROGRESS status: {e}")

    result = {
        "resource": "git_worktree",
        "chunk_index": chunk_index,
        "worktrees_created": 0,
        "worktrees_skipped": 0,
        "worktrees_failed": 0,
        "fork_commits_replayed": 0,
        "correlation_id": correlation_id,
        "error": None,
    }

    if not commit_shas:
        save_ingestion_result(self.redis, correlation_id, result)
        return result

    try:
        build_run_repo = RawBuildRunRepository(self.db)
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repo = raw_repo_repo.find_by_id(raw_repo_id)

        # Use github_repo_id for paths
        repo_path = get_repo_path(github_repo_id)
        worktrees_dir = get_worktrees_path(github_repo_id)
        worktrees_dir.mkdir(parents=True, exist_ok=True)

        if not repo_path.exists():
            result["error"] = "Repo not cloned"
            logger.error(f"{log_ctx} Repo not cloned at {repo_path}")
            save_ingestion_result(self.redis, correlation_id, result)
            return result

        # Get GitHub client for fork commit replay
        github_client = None
        try:
            from app.services.github.github_client import get_public_github_client

            github_client = get_public_github_client()
        except Exception as e:
            logger.warning(f"Failed to get GitHub client for fork replay: {e}")

        worktrees_created = 0
        worktrees_skipped = 0
        worktrees_failed = 0
        fork_commits_replayed = 0
        failed_commits: list[str] = []
        created_commits: list[str] = []

        for sha in commit_shas:
            # Quick check without lock
            worktree_path = worktrees_dir / sha[:12]
            if worktree_path.exists():
                worktrees_skipped += 1
                created_commits.append(sha)  # Skipped = already exists = success
                continue

            build_run = build_run_repo.find_by_commit_or_effective_sha(raw_repo_id, sha)

            try:
                # Process single commit with lock
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
                logger.exception(f"{log_ctx} Error processing commit {sha[:8]}: {e}")
                worktrees_failed += 1
                failed_commits.append(sha)

        logger.info(
            f"{log_ctx} Completed: created={worktrees_created}, "
            f"skipped={worktrees_skipped}, failed={worktrees_failed}"
        )

        result.update(
            {
                "worktrees_created": worktrees_created,
                "worktrees_skipped": worktrees_skipped,
                "worktrees_failed": worktrees_failed,
                "fork_commits_replayed": fork_commits_replayed,
                "failed_commits": failed_commits,
                "created_commits": created_commits,
            }
        )

    except SoftTimeLimitExceeded:
        # Task exceeded time limit - return result with what we accomplished
        processed_count = worktrees_created + worktrees_skipped + worktrees_failed
        remaining = len(commit_shas) - processed_count
        # Add unprocessed commits to failed list
        processed_shas = set(created_commits + failed_commits)
        unprocessed_commits = [sha for sha in commit_shas if sha not in processed_shas]
        failed_commits.extend(unprocessed_commits)

        logger.error(
            f"{log_ctx} TIMEOUT! Created {worktrees_created}, {remaining} commits not processed"
        )
        result.update(
            {
                "status": "timeout",
                "worktrees_created": worktrees_created,
                "worktrees_skipped": worktrees_skipped,
                "worktrees_failed": worktrees_failed + remaining,
                "fork_commits_replayed": fork_commits_replayed,
                "failed_commits": failed_commits,
                "error": f"Timeout: {remaining} commits not processed",
                "created_commits": created_commits,
            }
        )
        save_ingestion_result(self.redis, correlation_id, result)
        return result

    except Exception as e:
        # Check if we have retries left
        retries_left = self.max_retries - self.request.retries

        if retries_left > 0:
            # Still have retries - raise to trigger retry
            logger.warning(f"{log_ctx} Chunk failed, will retry ({retries_left} retries left): {e}")
            raise self.retry(exc=e, countdown=30) from e
        else:
            # No retries left - log error and return result to continue chain
            logger.error(
                f"{log_ctx} Chunk failed after {self.max_retries} retries, "
                f"continuing chain: {e}"
            )
            # Preserve what we accomplished before the error
            processed_count = worktrees_created + worktrees_skipped + worktrees_failed
            remaining = len(commit_shas) - processed_count
            # Add unprocessed commits to failed list
            processed_shas = set(created_commits + failed_commits)
            unprocessed_commits = [sha for sha in commit_shas if sha not in processed_shas]
            failed_commits.extend(unprocessed_commits)

            result.update(
                {
                    "error": str(e),
                    "worktrees_created": worktrees_created,
                    "worktrees_skipped": worktrees_skipped,
                    "worktrees_failed": worktrees_failed + remaining,
                    "fork_commits_replayed": fork_commits_replayed,
                    "failed_commits": failed_commits,
                    "created_commits": created_commits,
                }
            )

    save_ingestion_result(self.redis, correlation_id, result)
    return result


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
                                    build_run_repo.update_effective_sha(build_run.id, synthetic_sha)
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
    name="app.tasks.shared.aggregate_logs_results",
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

    for r in chunk_results:
        if not isinstance(r, dict):
            continue
        chunk_idx = r.get("chunk_index", "?")
        if r.get("error"):
            chunks_with_errors.append({"chunk_index": chunk_idx, "error": r.get("error")})
            logger.warning(f"{log_ctx} Chunk {chunk_idx} had error: {r.get('error')}")
        else:
            successful_chunks.append(r)

    # Aggregate results from all chunks (including those with partial success)
    total_downloaded = sum(
        r.get("logs_downloaded", 0) for r in chunk_results if isinstance(r, dict)
    )
    total_expired = sum(r.get("logs_expired", 0) for r in chunk_results if isinstance(r, dict))
    total_skipped = sum(r.get("logs_skipped", 0) for r in chunk_results if isinstance(r, dict))

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
    }

    save_ingestion_result(self.redis, correlation_id, result)
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
    base=PipelineTask,
    name="app.tasks.shared.download_logs_chunk",
    queue="ingestion",
    soft_time_limit=600,  # 10 min per chunk
    time_limit=660,
    max_retries=2,  # Will retry up to 2 times before giving up gracefully
)
def download_logs_chunk(
    self: PipelineTask,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    full_name: str = "",
    build_ids: Optional[List[str]] = None,
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    chunk_index: int = 0,
    total_chunks: int = 1,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Worker: Download logs for a chunk of builds.

    Runs as part of a chord, all chunks execute in parallel.
    This task retries on rate limit errors and returns error result after max retries.
    """

    task_id = self.request.id or "unknown"
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = (
        f"{corr_prefix}[logs][task={task_id}]"
        f"[repo={raw_repo_id}][chunk={chunk_index + 1}/{total_chunks}]"
    )

    logger.info(f"{log_ctx} Starting with {len(build_ids or [])} builds")

    # Update status to IN_PROGRESS for these builds
    if raw_repo_id and build_ids:
        try:
            model_config_repo = ModelRepoConfigRepository(self.db)
            import_build_repo = ModelImportBuildRepository(self.db)
            configs = model_config_repo.find_by_raw_repo(raw_repo_id)
            for config in configs:
                import_build_repo.update_resource_by_ci_run_ids(
                    str(config.id),
                    "build_logs",
                    build_ids,
                    ResourceStatus.IN_PROGRESS,
                )
        except Exception as e:
            logger.warning(f"{log_ctx} Failed to verify IN_PROGRESS status: {e}")

    # Initialize result with defaults
    result = {
        "resource": "build_logs",
        "chunk_index": chunk_index,
        "logs_downloaded": 0,
        "logs_expired": 0,
        "logs_skipped": 0,
        "correlation_id": correlation_id,
        "error": None,
    }

    if build_ids is None:
        build_ids = []

    try:
        # Check if we should stop (other chunk hit max expired)
        redis_client = self.redis
        session_key = f"logs_session:{raw_repo_id}"

        if redis_client.get(f"{session_key}:stop"):
            logger.info(f"{log_ctx} Skipped: stop flag set by another chunk")
            result["skipped"] = True
            result["reason"] = "early_stop"
            return result

        build_run_repo = RawBuildRunRepository(self.db)
        ci_provider_enum = CIProvider(ci_provider)
        provider_config = get_provider_config(ci_provider_enum)
        ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

        logs_downloaded = 0
        logs_expired = 0
        logs_skipped = 0
        max_log_size = settings.GIT_MAX_LOG_SIZE_MB * 1024 * 1024
        failed_log_ids: list[str] = []
        expired_log_ids: list[str] = []
        downloaded_log_ids: list[str] = []
        skipped_log_ids: list[str] = []

        max_consecutive = int(redis_client.get(f"{session_key}:max_expired") or 10)

        async def run_batch():
            for build_id in build_ids:
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

                nonlocal logs_downloaded, logs_expired, logs_skipped
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

                if res["status"] == "stopped":
                    break

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_batch())
        finally:
            loop.close()

        logger.info(
            f"{log_ctx} Completed: downloaded={logs_downloaded}, "
            f"expired={logs_expired}, skipped={logs_skipped}"
        )

        result["logs_downloaded"] = logs_downloaded
        result["logs_expired"] = logs_expired
        result["logs_skipped"] = logs_skipped
        result["failed_log_ids"] = failed_log_ids
        result["expired_log_ids"] = expired_log_ids
        result["downloaded_log_ids"] = downloaded_log_ids
        result["skipped_log_ids"] = skipped_log_ids
        return result

    except SoftTimeLimitExceeded:
        # Task exceeded time limit - return result with what we accomplished
        processed = logs_downloaded + logs_expired + logs_skipped
        remaining = len(build_ids) - processed if build_ids else 0
        logger.error(
            f"{log_ctx} TIMEOUT! Downloaded {logs_downloaded}, {remaining} builds not processed"
        )
        result.update(
            {
                "status": "timeout",
                "logs_downloaded": logs_downloaded,
                "logs_expired": logs_expired,
                "logs_skipped": logs_skipped,
                "failed_log_ids": failed_log_ids,
                "expired_log_ids": expired_log_ids,
                "downloaded_log_ids": downloaded_log_ids,
                "skipped_log_ids": skipped_log_ids,
                "error": f"Timeout: {remaining} builds not processed",
            }
        )
        return result

    except Exception as e:
        retries_left = self.max_retries - self.request.retries
        logger.error(f"{log_ctx} Error (retries_left={retries_left}): {e}", exc_info=True)

        if retries_left > 0:
            # Retry with exponential backoff
            countdown = 60 * (self.request.retries + 1)
            raise self.retry(exc=e, countdown=countdown) from e
        else:
            # Max retries exhausted - return error result, don't break chain
            logger.warning(f"{log_ctx} Max retries exhausted, returning error result")
            result.update(
                {
                    "error": str(e),
                    "logs_downloaded": logs_downloaded,
                    "logs_expired": logs_expired,
                    "logs_skipped": logs_skipped,
                    "failed_log_ids": failed_log_ids,
                    "expired_log_ids": expired_log_ids,
                    "downloaded_log_ids": downloaded_log_ids,
                    "skipped_log_ids": skipped_log_ids,
                }
            )
            return result
