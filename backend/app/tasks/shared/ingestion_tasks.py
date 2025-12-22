"""
Shared Ingestion Tasks - Generic tasks for both model and dataset pipelines.

These tasks are shared between model_ingestion.py and dataset_ingestion.py
to avoid code duplication. They work with any repository/build type.

Features:
- Clone/update git repositories (with installation token support)
- Create git worktrees (with fork commit replay support)
- Download build logs from CI providers
- Optional status publishing for UI updates
"""

import asyncio
import logging
import subprocess
from typing import Any, Dict, List

from app.celery_app import celery_app
from app.ci_providers import CIProvider, get_ci_provider, get_provider_config
from app.config import settings
from app.core.redis import RedisLock
from app.paths import (
    get_build_logs_path,
    get_repo_path,
    get_worktrees_path,
)
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.github.exceptions import GithubRateLimitError, GithubRetryableError
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, key: str, calls_per_second: float = 5.0):
        self.key = f"ratelimit:{key}"
        self.min_interval = 1.0 / calls_per_second

    def wait(self):
        """Wait until rate limit allows next call."""
        import time

        import redis

        redis_client = redis.from_url(settings.REDIS_URL)
        while True:
            now = time.time()
            last_call = redis_client.get(self.key)
            if last_call is None:
                # First call
                redis_client.set(self.key, now, ex=60)
                return
            last_time = float(last_call)
            elapsed = now - last_time
            if elapsed >= self.min_interval:
                redis_client.set(self.key, now, ex=60)
                return
            # Wait for remaining time
            time.sleep(self.min_interval - elapsed)


def _publish_status(repo_id: str, status: str, message: str = ""):
    """Publish status update to Redis for real-time UI updates."""
    try:
        import json

        import redis

        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.publish(
            "events",
            json.dumps(
                {
                    "type": "REPO_UPDATE",
                    "payload": {
                        "repo_id": repo_id,
                        "status": status,
                        "message": message,
                    },
                }
            ),
        )
    except Exception as e:
        logger.error(f"Failed to publish status update: {e}")


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.clone_repo",
    queue="ingestion",
    soft_time_limit=600,  # 10 min warning
    time_limit=660,  # 11 min hard kill
    autoretry_for=(subprocess.CalledProcessError, TimeoutError),
    retry_kwargs={"max_retries": 3, "countdown": 360},
)
def clone_repo(
    self: PipelineTask,
    prev_result: Any = None,  # Allow chaining from previous task
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    full_name: str = "",
    publish_status: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Clone or update git repository.

    Works for both model and dataset pipelines.
    Supports installation token for private repos.
    Uses github_repo_id for folder path (stable across renames).
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[clone][repo={full_name}]"

    logger.info(f"{log_ctx} Starting clone/update")

    if publish_status and raw_repo_id:
        _publish_status(raw_repo_id, "importing", "Cloning repository...")

    repo_path = get_repo_path(github_repo_id)

    with RedisLock(f"clone:{github_repo_id}", timeout=700, blocking_timeout=60):
        try:
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

            if publish_status and raw_repo_id:
                _publish_status(raw_repo_id, "importing", "Repository cloned successfully")

            result = {
                "raw_repo_id": raw_repo_id,
                "github_repo_id": github_repo_id,
                "status": "cloned",
                "path": str(repo_path),
                "correlation_id": correlation_id,
            }

            # Preserve previous result data for chaining
            if isinstance(prev_result, dict):
                return {**prev_result, **result}
            return result

        except subprocess.CalledProcessError as e:
            logger.error(f"{log_ctx} Git operation failed: {e.stderr}")
            raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.create_worktree_chunk",
    queue="ingestion",
    soft_time_limit=300,  # 5 min per chunk
    time_limit=360,
    autoretry_for=(subprocess.CalledProcessError, subprocess.TimeoutExpired),
    retry_kwargs={"max_retries": 2, "countdown": 30},
)
def create_worktree_chunk(
    self: PipelineTask,
    prev_result: Any = None,  # Allow chaining
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    commit_shas: List[str] | None = None,
    publish_status: bool = False,
    chunk_index: int = 0,
    total_chunks: int = 1,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Worker: Create worktrees for a chunk of commits.

    Runs as part of a chain, each chunk executes sequentially.
    """
    task_id = self.request.id or "unknown"
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = (
        f"{corr_prefix}[worktree][task={task_id}]"
        f"[repo={raw_repo_id}][chunk={chunk_index + 1}/{total_chunks}]"
    )

    logger.info(f"{log_ctx} Starting with {len(commit_shas or [])} commits")

    if commit_shas is None:
        commit_shas = []

    build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)
    raw_repo = raw_repo_repo.find_by_id(raw_repo_id)

    # Use github_repo_id for paths
    repo_path = get_repo_path(github_repo_id)
    worktrees_dir = get_worktrees_path(github_repo_id)
    worktrees_dir.mkdir(parents=True, exist_ok=True)

    if not repo_path.exists():
        return {"error": "Repo not cloned", "worktrees_created": 0}

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

    for sha in commit_shas:
        worktree_path = worktrees_dir / sha[:12]

        # Quick check without lock
        if worktree_path.exists():
            worktrees_skipped += 1
            continue

        build_run = build_run_repo.find_by_commit_or_effective_sha(raw_repo_id, sha)

        # Use lock to prevent race condition with integration_scan
        try:
            with RedisLock(
                f"worktree:{github_repo_id}:{sha[:12]}",
                timeout=120,
                blocking_timeout=60,
            ):
                # Double-check after acquiring lock
                if worktree_path.exists():
                    worktrees_skipped += 1
                    continue

                # Check if commit exists
                result = subprocess.run(
                    ["git", "cat-file", "-e", sha],
                    cwd=str(repo_path),
                    capture_output=True,
                    timeout=10,
                )

                if result.returncode != 0:
                    # Attempt fork replay
                    if github_client and raw_repo:
                        try:
                            from app.utils.git import ensure_commit_exists

                            synthetic_sha = ensure_commit_exists(
                                repo_path=repo_path,
                                commit_sha=sha,
                                repo_slug=raw_repo.full_name,
                                github_client=github_client,
                            )
                            if synthetic_sha:
                                if build_run:
                                    build_run_repo.update_effective_sha(build_run.id, synthetic_sha)
                                sha = synthetic_sha
                                fork_commits_replayed += 1
                            else:
                                worktrees_skipped += 1
                                continue
                        except Exception as e:
                            logger.warning(f"Fork replay failed for {sha[:8]}: {e}")
                            worktrees_skipped += 1
                            continue
                    else:
                        worktrees_skipped += 1
                        continue

                # Create worktree
                worktree_path = worktrees_dir / sha[:12]
                subprocess.run(
                    ["git", "worktree", "add", "--detach", str(worktree_path), sha],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                worktrees_created += 1

        except subprocess.CalledProcessError as e:
            logger.error(
                f"{log_ctx} Failed to create worktree for {sha[:8]}: "
                f"cmd={e.cmd}, returncode={e.returncode}, stderr={e.stderr}"
            )
            worktrees_failed += 1
        except subprocess.TimeoutExpired as e:
            logger.error(f"{log_ctx} Timeout creating worktree for {sha[:8]}: {e}")
            worktrees_failed += 1
        except Exception as e:
            logger.exception(f"{log_ctx} Unexpected error creating worktree for {sha[:8]}: {e}")
            worktrees_failed += 1

    if publish_status and raw_repo_id:
        msg = (
            f"Chunk {chunk_index + 1}/{total_chunks}: "
            f"{worktrees_created} created, {worktrees_skipped} skipped"
        )
        _publish_status(raw_repo_id, "importing", msg)

    logger.info(
        f"{log_ctx} Completed: created={worktrees_created}, "
        f"skipped={worktrees_skipped}, failed={worktrees_failed}"
    )

    return {
        "chunk_index": chunk_index,
        "worktrees_created": worktrees_created,
        "worktrees_skipped": worktrees_skipped,
        "worktrees_failed": worktrees_failed,
        "fork_commits_replayed": fork_commits_replayed,
        "correlation_id": correlation_id,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.finalize_worktrees",
    queue="ingestion",
    soft_time_limit=60,
    time_limit=120,
)
def finalize_worktrees(
    self: PipelineTask,
    prev_results: Any = None,  # Results from chained chunk tasks
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    total_chunks: int = 0,
    publish_status: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Finalize worktree creation after chain completes.

    Aggregates results from chunk tasks and publishes completion status.
    This task is the last step in the worktree creation chain.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[worktree_finalize][repo={raw_repo_id}]"

    # Aggregate results if prev_results is a list from chain
    if isinstance(prev_results, list):
        total_created = sum(
            r.get("worktrees_created", 0) for r in prev_results if isinstance(r, dict)
        )
        total_skipped = sum(
            r.get("worktrees_skipped", 0) for r in prev_results if isinstance(r, dict)
        )
        total_failed = sum(
            r.get("worktrees_failed", 0) for r in prev_results if isinstance(r, dict)
        )
    elif isinstance(prev_results, dict):
        total_created = prev_results.get("worktrees_created", 0)
        total_skipped = prev_results.get("worktrees_skipped", 0)
        total_failed = prev_results.get("worktrees_failed", 0)
    else:
        total_created = 0
        total_skipped = 0
        total_failed = 0

    logger.info(
        f"{log_ctx} Finalized: created={total_created}, "
        f"skipped={total_skipped}, failed={total_failed}"
    )

    if publish_status and raw_repo_id:
        _publish_status(
            raw_repo_id,
            "importing",
            f"Worktrees ready: {total_created} created, {total_skipped} skipped",
        )

    return {
        "status": "completed",
        "worktrees_created": total_created,
        "worktrees_skipped": total_skipped,
        "worktrees_failed": total_failed,
        "chunks_completed": total_chunks,
        "correlation_id": correlation_id,
    }


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
    publish_status: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Chord callback: Aggregate results from parallel log download chunks.

    This task receives results from all chunk tasks after they complete.
    Publishes final status update.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = f"{corr_prefix}[logs_aggregate][repo={raw_repo_id}]"

    # Aggregate results from all chunks
    total_downloaded = sum(
        r.get("logs_downloaded", 0) for r in chunk_results if isinstance(r, dict)
    )
    total_expired = sum(r.get("logs_expired", 0) for r in chunk_results if isinstance(r, dict))
    total_skipped = sum(r.get("logs_skipped", 0) for r in chunk_results if isinstance(r, dict))

    logger.info(
        f"{log_ctx} Aggregated: downloaded={total_downloaded}, "
        f"expired={total_expired}, skipped={total_skipped}"
    )

    if publish_status and raw_repo_id:
        _publish_status(
            raw_repo_id,
            "importing",
            f"Logs ready: {total_downloaded} downloaded, {total_expired} expired",
        )

    return {
        "status": "completed",
        "logs_downloaded": total_downloaded,
        "logs_expired": total_expired,
        "logs_skipped": total_skipped,
        "chunks_completed": total_chunks,
        "correlation_id": correlation_id,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.download_logs_chunk",
    queue="ingestion",
    soft_time_limit=600,  # 10 min per chunk
    time_limit=660,
    autoretry_for=(GithubRateLimitError, GithubRetryableError),
    retry_kwargs={"max_retries": 2, "countdown": 60},
)
def download_logs_chunk(
    self: PipelineTask,
    raw_repo_id: str = "",
    github_repo_id: int = 0,
    full_name: str = "",
    build_ids: List[str] | None = None,
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    publish_status: bool = False,
    chunk_index: int = 0,
    total_chunks: int = 1,
    force_download: bool = False,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Worker: Download logs for a chunk of builds.

    Runs as part of a chord, all chunks execute in parallel.
    """
    import redis

    from app.services.github.exceptions import GithubLogsUnavailableError

    task_id = self.request.id or "unknown"
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    log_ctx = (
        f"{corr_prefix}[logs][task={task_id}]"
        f"[repo={raw_repo_id}][chunk={chunk_index + 1}/{total_chunks}]"
    )

    logger.info(f"{log_ctx} Starting with {len(build_ids or [])} builds")

    if build_ids is None:
        build_ids = []

    # Check if we should stop (other chunk hit max expired)
    redis_client = redis.from_url(settings.REDIS_URL)
    session_key = f"logs_session:{raw_repo_id}"

    if redis_client.get(f"{session_key}:stop"):
        logger.info(f"Chunk {chunk_index} skipped: stop flag set by another chunk")
        return {"chunk_index": chunk_index, "skipped": True, "reason": "early_stop"}

    build_run_repo = RawBuildRunRepository(self.db)
    ci_provider_enum = CIProvider(ci_provider)
    provider_config = get_provider_config(ci_provider_enum)
    ci_instance = get_ci_provider(ci_provider_enum, provider_config, db=self.db)

    logs_downloaded = 0
    logs_expired = 0
    logs_skipped = 0
    max_log_size = settings.MAX_LOG_SIZE_MB * 1024 * 1024

    rate_limit = getattr(settings, "API_RATE_LIMIT_PER_SECOND", 5.0)
    github_limiter = RateLimiter(f"github_logs:{raw_repo_id}", calls_per_second=rate_limit)

    max_consecutive = int(redis_client.get(f"{session_key}:max_expired") or 10)

    async def download_one(build_id: str) -> str:
        nonlocal logs_downloaded, logs_expired, logs_skipped

        # Check stop flag before each download
        if redis_client.get(f"{session_key}:stop"):
            return "stopped"

        build_run = build_run_repo.find_by_repo_and_build_id(raw_repo_id, build_id)
        if build_run and build_run.logs_available:
            # Verify log files actually exist on disk
            expected_logs_dir = get_build_logs_path(github_repo_id, build_id)
            if expected_logs_dir.exists() and any(expected_logs_dir.glob("*.log")):
                logs_skipped += 1
                return "skipped"
            else:
                # logs_available is True but files missing - reset and re-download
                logger.info(f"Log files missing for {build_id}, re-downloading...")
                build_run_repo.update_one(
                    str(build_run.id),
                    {"logs_available": False, "logs_path": None},
                )

        try:
            build_logs_dir = get_build_logs_path(github_repo_id, build_id)
            build_logs_dir.mkdir(parents=True, exist_ok=True)

            fetch_kwargs = {"build_id": f"{full_name}:{build_id}"}

            github_limiter.wait()
            log_files = await ci_instance.fetch_build_logs(**fetch_kwargs)

            if not log_files:
                if build_run:
                    build_run_repo.update_one(
                        str(build_run.id),
                        {"logs_available": False, "logs_expired": True},
                    )
                logs_expired += 1

                # Update consecutive counter in Redis
                consecutive = redis_client.incr(f"{session_key}:consecutive")
                if consecutive >= max_consecutive:
                    redis_client.set(f"{session_key}:stop", 1, ex=3600)
                    logger.info(f"Setting stop flag: {consecutive} consecutive expired")
                return "expired"

            # Reset consecutive counter on success
            redis_client.set(f"{session_key}:consecutive", 0)

            saved_files = []
            for log_file in log_files:
                if log_file.size_bytes > max_log_size:
                    continue
                log_path = build_logs_dir / f"{log_file.job_name}.log"
                log_path.write_text(log_file.content)
                saved_files.append(str(log_path))

            if saved_files:
                if build_run:
                    build_run_repo.update_one(
                        str(build_run.id),
                        {"logs_path": str(build_logs_dir), "logs_available": True},
                    )
                logs_downloaded += 1
                return "downloaded"
            else:
                logs_expired += 1
                return "expired"

        except GithubLogsUnavailableError:
            if build_run:
                build_run_repo.update_one(
                    str(build_run.id),
                    {"logs_available": False, "logs_expired": True},
                )
            logs_expired += 1
            consecutive = redis_client.incr(f"{session_key}:consecutive")
            if consecutive >= max_consecutive:
                redis_client.set(f"{session_key}:stop", 1, ex=3600)
            return "expired"
        except Exception as e:
            logger.exception(f"{log_ctx} Failed to download logs for build {build_id}: {e}")
            return "failed"

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for build_id in build_ids:
            result = loop.run_until_complete(download_one(build_id))
            if result == "stopped":
                break
    finally:
        loop.close()

    if publish_status and raw_repo_id:
        msg = (
            f"Logs chunk {chunk_index + 1}/{total_chunks}: "
            f"{logs_downloaded} downloaded, {logs_expired} expired"
        )
        _publish_status(raw_repo_id, "importing", msg)

    logger.info(
        f"{log_ctx} Completed: downloaded={logs_downloaded}, "
        f"expired={logs_expired}, skipped={logs_skipped}"
    )

    return {
        "chunk_index": chunk_index,
        "logs_downloaded": logs_downloaded,
        "logs_expired": logs_expired,
        "logs_skipped": logs_skipped,
        "correlation_id": correlation_id,
    }
