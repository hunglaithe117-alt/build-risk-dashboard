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

import logging
import subprocess
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId
from celery import chain, group

from app.celery_app import celery_app
from app.config import settings
from app.tasks.base import PipelineTask
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.ci_providers import CIProvider, get_provider_config, get_ci_provider
from app.services.github.exceptions import GithubRateLimitError
from app.paths import REPOS_DIR, WORKTREES_DIR, LOGS_DIR

logger = logging.getLogger(__name__)

from app.core.redis import RedisLock


class RateLimiter:
    def __init__(self, key: str, calls_per_second: float = 5.0):
        self.key = f"ratelimit:{key}"
        self.min_interval = 1.0 / calls_per_second

    def wait(self):
        """Wait until rate limit allows next call."""
        import redis
        import time

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
        import redis
        import json

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
    full_name: str = "",
    publish_status: bool = False,
    installation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Clone or update git repository.

    Works for both model and dataset pipelines.
    Supports installation token for private repos.
    """
    if publish_status and raw_repo_id:
        _publish_status(raw_repo_id, "importing", "Cloning repository...")

    repo_path = REPOS_DIR / raw_repo_id

    with RedisLock(f"clone:{raw_repo_id}", timeout=700, blocking_timeout=60):
        try:
            if repo_path.exists():
                logger.info(f"Updating existing clone for {full_name}")
                subprocess.run(
                    ["git", "fetch", "--all", "--prune"],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
            else:
                logger.info(f"Cloning {full_name} to {repo_path}")
                clone_url = f"https://github.com/{full_name}.git"

                # For private repos, use installation token
                if installation_id:
                    from app.services.github.github_app import get_installation_token

                    token = get_installation_token(installation_id, self.db)
                    clone_url = (
                        f"https://x-access-token:{token}@github.com/{full_name}.git"
                    )

                subprocess.run(
                    ["git", "clone", "--bare", clone_url, str(repo_path)],
                    check=True,
                    capture_output=True,
                    timeout=600,
                )

            if publish_status and raw_repo_id:
                _publish_status(
                    raw_repo_id, "importing", "Repository cloned successfully"
                )

            result = {
                "raw_repo_id": raw_repo_id,
                "status": "cloned",
                "path": str(repo_path),
            }

            # Preserve previous result data for chaining
            if isinstance(prev_result, dict):
                return {**prev_result, **result}
            return result

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed for {full_name}: {e.stderr}")
            raise


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.create_worktrees",
    queue="ingestion",
    soft_time_limit=300,  # 5 min (just dispatches chunks)
    time_limit=360,
)
def create_worktrees(
    self: PipelineTask,
    raw_repo_id: str = "",
    commit_shas: List[str] = [],
    publish_status: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator: Dispatch worktree creation in chunks.

    Each chunk runs as a separate task for better fault tolerance.
    """

    if not commit_shas:
        return {"worktrees_created": 0, "worktrees_skipped": 0}

    # Deduplicate
    unique_shas = list(dict.fromkeys(commit_shas))

    if publish_status and raw_repo_id:
        _publish_status(
            raw_repo_id,
            "importing",
            f"Creating worktrees for {len(unique_shas)} commits...",
        )

    # Dispatch chunks
    chunk_size = getattr(settings, "WORKTREE_BATCH_SIZE", 50)
    chunks_dispatched = 0

    for i in range(0, len(unique_shas), chunk_size):
        chunk = unique_shas[i : i + chunk_size]
        create_worktree_chunk.delay(
            raw_repo_id=raw_repo_id,
            commit_shas=chunk,
            publish_status=publish_status,
            chunk_index=i // chunk_size,
            total_chunks=(len(unique_shas) + chunk_size - 1) // chunk_size,
        )
        chunks_dispatched += 1

    logger.info(
        f"Dispatched {chunks_dispatched} worktree chunks for repo {raw_repo_id}"
    )

    return {
        "worktree_chunks_dispatched": chunks_dispatched,
        "total_commits": len(unique_shas),
    }


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
    raw_repo_id: str,
    commit_shas: List[str],
    publish_status: bool = False,
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> Dict[str, Any]:
    """
    Worker: Create worktrees for a chunk of commits.
    """
    build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)
    raw_repo = raw_repo_repo.find_by_id(raw_repo_id)

    repo_path = REPOS_DIR / raw_repo_id
    worktrees_dir = WORKTREES_DIR / raw_repo_id
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
        if worktree_path.exists():
            worktrees_skipped += 1
            continue

        build_run = build_run_repo.find_by_commit_or_effective_sha(raw_repo_id, sha)

        try:
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
                        from app.services.commit_replay import ensure_commit_exists

                        synthetic_sha = ensure_commit_exists(
                            repo_path=repo_path,
                            commit_sha=sha,
                            repo_slug=raw_repo.full_name,
                            github_client=github_client,
                        )
                        if synthetic_sha:
                            if build_run:
                                build_run_repo.update_effective_sha(
                                    build_run.id, synthetic_sha
                                )
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
            logger.warning(f"Failed to create worktree for {sha[:8]}: {e}")
            worktrees_failed += 1
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout creating worktree for {sha[:8]}")
            worktrees_failed += 1

    if publish_status and raw_repo_id:
        _publish_status(
            raw_repo_id,
            "importing",
            f"Chunk {chunk_index + 1}/{total_chunks}: {worktrees_created} created, {worktrees_skipped} skipped",
        )

    return {
        "chunk_index": chunk_index,
        "worktrees_created": worktrees_created,
        "worktrees_skipped": worktrees_skipped,
        "worktrees_failed": worktrees_failed,
        "fork_commits_replayed": fork_commits_replayed,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.download_build_logs",
    queue="ingestion",
    soft_time_limit=300,  # 5 min (just dispatches chunks)
    time_limit=360,
)
def download_build_logs(
    self: PipelineTask,
    prev_result: Dict[str, Any] = None,
    raw_repo_id: str = "",
    full_name: str = "",
    build_ids: List[str] = [],
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    installation_id: Optional[str] = None,
    max_consecutive_expired: int = 10,
    publish_status: bool = False,
) -> Dict[str, Any]:
    """
    Orchestrator: Dispatch log downloads in chunks.

    Uses Redis shared state for consecutive_expired tracking across chunks.
    """
    import redis

    prev_result = prev_result or {}
    build_ids = build_ids or prev_result.get("build_ids", [])

    if not build_ids:
        return {**prev_result, "logs_downloaded": 0, "logs_expired": 0}

    # Deduplicate
    unique_build_ids = list(dict.fromkeys(build_ids))

    if publish_status and raw_repo_id:
        _publish_status(
            raw_repo_id,
            "importing",
            f"Downloading logs for {len(unique_build_ids)} builds...",
        )

    # Initialize Redis state for this download session
    redis_client = redis.from_url(settings.REDIS_URL)
    session_key = f"logs_session:{raw_repo_id}"
    redis_client.delete(f"{session_key}:consecutive")
    redis_client.delete(f"{session_key}:stop")
    redis_client.set(f"{session_key}:max_expired", max_consecutive_expired, ex=3600)

    # Dispatch chunks
    chunk_size = getattr(settings, "DOWNLOAD_LOGS_BATCH_SIZE", 50)
    chunks_dispatched = 0

    for i in range(0, len(unique_build_ids), chunk_size):
        chunk = unique_build_ids[i : i + chunk_size]
        download_logs_chunk.delay(
            raw_repo_id=raw_repo_id,
            full_name=full_name,
            build_ids=chunk,
            ci_provider=ci_provider,
            installation_id=installation_id,
            publish_status=publish_status,
            chunk_index=i // chunk_size,
            total_chunks=(len(unique_build_ids) + chunk_size - 1) // chunk_size,
        )
        chunks_dispatched += 1

    logger.info(
        f"Dispatched {chunks_dispatched} log download chunks for repo {raw_repo_id}"
    )

    return {
        **prev_result,
        "log_chunks_dispatched": chunks_dispatched,
        "total_builds": len(unique_build_ids),
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.shared.download_logs_chunk",
    queue="ingestion",
    soft_time_limit=600,  # 10 min per chunk
    time_limit=660,
    autoretry_for=(GithubRateLimitError,),
    retry_kwargs={"max_retries": 2, "countdown": 60},
)
def download_logs_chunk(
    self: PipelineTask,
    raw_repo_id: str,
    full_name: str,
    build_ids: List[str],
    ci_provider: str = CIProvider.GITHUB_ACTIONS.value,
    installation_id: Optional[str] = None,
    publish_status: bool = False,
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> Dict[str, Any]:
    """
    Worker: Download logs for a chunk of builds.

    Uses Redis shared state to track consecutive_expired across all chunks.
    Stops early if global stop flag is set.
    """
    import redis
    from app.services.github.exceptions import GithubLogsUnavailableError

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
    github_limiter = RateLimiter(
        f"github_logs:{raw_repo_id}", calls_per_second=rate_limit
    )

    max_consecutive = int(redis_client.get(f"{session_key}:max_expired") or 10)

    async def download_one(build_id: str) -> str:
        nonlocal logs_downloaded, logs_expired, logs_skipped

        # Check stop flag before each download
        if redis_client.get(f"{session_key}:stop"):
            return "stopped"

        build_run = build_run_repo.find_by_repo_and_build_id(raw_repo_id, build_id)
        if build_run and build_run.logs_available:
            logs_skipped += 1
            return "skipped"

        try:
            build_logs_dir = LOGS_DIR / raw_repo_id / build_id
            build_logs_dir.mkdir(parents=True, exist_ok=True)

            composite_id = f"{full_name}:{build_id}"
            fetch_kwargs = {"build_id": composite_id}
            if ci_provider_enum == CIProvider.GITHUB_ACTIONS and installation_id:
                fetch_kwargs["installation_id"] = installation_id

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
            logger.warning(f"Failed to download logs for build {build_id}: {e}")
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
        _publish_status(
            raw_repo_id,
            "importing",
            f"Logs chunk {chunk_index + 1}/{total_chunks}: {logs_downloaded} downloaded, {logs_expired} expired",
        )

    return {
        "chunk_index": chunk_index,
        "logs_downloaded": logs_downloaded,
        "logs_expired": logs_expired,
        "logs_skipped": logs_skipped,
    }
