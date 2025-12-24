from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from app.config import settings
from app.paths import get_repo_path, get_worktree_path
from app.services.github.github_client import GitHubClient

logger = logging.getLogger(__name__)


class MissingForkCommitError(RuntimeError):
    def __init__(self, commit_sha: str, message: str) -> None:
        self.commit_sha = commit_sha
        super().__init__(message)


@dataclass
class ReplayCommit:
    sha: str
    patch: str
    message: str
    author_name: str
    author_email: str
    author_date: str


@dataclass
class ReplayPlan:
    base_sha: str
    commits: List[ReplayCommit]


def ensure_commit_exists(
    repo_path: Path,
    commit_sha: str,
    repo_slug: str,
    github_client: GitHubClient,
) -> Optional[str]:
    """
    Ensures that the given commit SHA exists in the local repository.
    If missing (e.g. fork commit), attempts to fetch or reconstruct it.

    Args:
        repo_path: Path to bare git repo
        commit_sha: Target commit SHA
        repo_slug: Repo full name (owner/repo)
        github_client: GitHubClient to use for API calls.

    Returns:
        SHA to use (original or synthetic), or None if failed
    """
    if _commit_exists(repo_path, commit_sha):
        return commit_sha

    logger.info(f"Commit {commit_sha} not found locally. Attempting to fetch...")

    # Try fetching directly (some servers allow fetching by SHA)
    try:
        _run_git(repo_path, ["fetch", "origin", commit_sha])
        if _commit_exists(repo_path, commit_sha):
            return commit_sha
    except subprocess.CalledProcessError:
        logger.warning(f"Failed to fetch commit {commit_sha}")
        pass

    logger.info(f"Direct fetch failed. Attempting to replay fork commit {commit_sha}...")

    try:
        plan = build_replay_plan(
            repo_slug=repo_slug,
            target_sha=commit_sha,
            commit_exists=lambda sha: _commit_exists(repo_path, sha),
            github_client=github_client,
        )
        synthetic_sha = apply_replay_plan(repo_path, plan, target_sha=commit_sha)
        return synthetic_sha
    except MissingForkCommitError as e:
        logger.warning(f"Cannot replay fork commit: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to replay commit {commit_sha}: {e}")
        return None


def build_replay_plan(
    repo_slug: str,
    target_sha: str,
    commit_exists: Callable[[str], bool],
    github_client: GitHubClient,
    max_depth: int = -1,
) -> ReplayPlan:
    """
    Constructs a plan to replay missing commits by traversing up ancestry
    until a locally existing commit is found.
    """
    if max_depth == -1:
        from app.config import settings

        max_depth = settings.COMMIT_REPLAY_MAX_DEPTH
    if commit_exists(target_sha):
        raise ValueError(f"Commit {target_sha} already exists")

    missing_commits: List[ReplayCommit] = []
    current = target_sha
    depth = 0
    visited = set()

    while True:
        depth += 1
        if depth > max_depth:
            raise MissingForkCommitError(
                target_sha, f"Exceeded parent traversal limit ({max_depth})"
            )

        # Get commit info using GitHubClient
        try:
            data = github_client.get_commit(repo_slug, current)
        except Exception as e:
            raise MissingForkCommitError(current, f"GitHub API error: {e}") from e

        parents = data.get("parents", [])
        if len(parents) != 1:
            raise MissingForkCommitError(
                current, "Cannot replay commit with zero or multiple parents (merge)"
            )

        parent_sha = parents[0]["sha"]

        # Get patch using GitHubClient
        try:
            patch_content = github_client.get_commit_patch(repo_slug, current)
        except Exception as e:
            raise MissingForkCommitError(current, f"Failed to download patch: {e}") from e

        commit_info = data.get("commit", {})
        author_info = commit_info.get("author", {})

        replay_commit = ReplayCommit(
            sha=current,
            patch=patch_content,
            message=commit_info.get("message", ""),
            author_name=author_info.get("name", "Unknown"),
            author_email=author_info.get("email", "unknown@example.com"),
            author_date=author_info.get("date", ""),
        )
        missing_commits.append(replay_commit)

        if commit_exists(parent_sha):
            missing_commits.reverse()
            logger.info(
                f"Found base commit {parent_sha}. Replaying {len(missing_commits)} commits."
            )
            return ReplayPlan(base_sha=parent_sha, commits=missing_commits)

        if parent_sha in visited:
            raise MissingForkCommitError(current, "Loop detected in commit history")

        visited.add(current)
        current = parent_sha


def apply_replay_plan(repo_path: Path, plan: ReplayPlan, target_sha: str) -> str:
    """
    Applies the replay plan using a temporary worktree (for bare repos).
    Returns SHA of the final synthetic commit.
    """
    import os
    import shutil

    # Create temporary worktree for replay (bare repos don't have working tree)
    worktree_base = repo_path.parent.parent / "worktrees" / repo_path.name
    worktree_base.mkdir(parents=True, exist_ok=True)
    replay_worktree = worktree_base / f"replay-{target_sha[:8]}"

    try:
        # Clean up any existing worktree
        if replay_worktree.exists():
            _run_git(repo_path, ["worktree", "remove", str(replay_worktree), "--force"])
            if replay_worktree.exists():
                shutil.rmtree(replay_worktree, ignore_errors=True)

        # Prune stale worktree references
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_path),
            capture_output=True,
            check=False,
        )

        # Create worktree at base commit
        _run_git(
            repo_path,
            ["worktree", "add", "--detach", str(replay_worktree), plan.base_sha],
        )

        last_sha = plan.base_sha

        for commit in plan.commits:
            logger.info(f"Replaying commit {commit.sha[:8]}...")

            # Apply patch in worktree
            try:
                subprocess.run(
                    ["git", "apply", "--index", "--whitespace=nowarn"],
                    cwd=str(replay_worktree),
                    input=commit.patch,
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=60,  # Prevent hanging on large patches
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Timeout applying patch for {commit.sha}")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to apply patch for {commit.sha}: {e.stderr}")

            # Commit with original author info
            env = os.environ.copy()
            env.update(
                {
                    "GIT_AUTHOR_NAME": commit.author_name,
                    "GIT_AUTHOR_EMAIL": commit.author_email,
                    "GIT_AUTHOR_DATE": commit.author_date,
                    "GIT_COMMITTER_NAME": "Commit Replay",
                    "GIT_COMMITTER_EMAIL": "commit-replay@local",
                }
            )

            try:
                subprocess.run(
                    ["git", "commit", "-m", commit.message],
                    cwd=str(replay_worktree),
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=30,  # Prevent hanging on commit
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Timeout committing {commit.sha}")
            except subprocess.CalledProcessError:
                # Try with --allow-empty if no changes
                subprocess.run(
                    ["git", "commit", "-m", commit.message, "--allow-empty"],
                    cwd=str(replay_worktree),
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )

            # Get the new SHA
            last_sha = _run_git(replay_worktree, ["rev-parse", "HEAD"])

        logger.info(f"Replay complete. Synthetic commit: {last_sha} (from {target_sha})")
        return last_sha

    finally:
        # Cleanup worktree
        try:
            _run_git(repo_path, ["worktree", "remove", str(replay_worktree), "--force"])
        except Exception:
            pass
        if replay_worktree.exists():
            shutil.rmtree(replay_worktree, ignore_errors=True)


def _run_git(cwd: Path, args: List[str], timeout: int = 120) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def _commit_exists(cwd: Path, sha: str) -> bool:
    try:
        subprocess.run(
            ["git", "cat-file", "-e", sha],
            cwd=str(cwd),
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def ensure_worktree(github_repo_id: int, commit_sha: str, full_name: str) -> Optional[Path]:
    """
    Ensure worktree exists for a specific commit.

    Uses RedisLock to coordinate with other workers.
    Creates bare repo if not exists, handles fork commits via replay, then creates worktree.

    Args:
        github_repo_id: GitHub's internal repository ID
        commit_sha: Full commit SHA
        full_name: Repository full name (owner/repo)

    Returns:
        Path to worktree if successful, None otherwise
    """
    from app.core.redis import RedisLock

    if not github_repo_id:
        logger.warning("No github_repo_id provided, cannot create worktree")
        return None

    worktree_path = get_worktree_path(github_repo_id, commit_sha)
    repo_path = get_repo_path(github_repo_id)

    # Quick check - already exists
    if worktree_path.exists() and (worktree_path / ".git").exists():
        logger.debug(f"Using existing worktree: {worktree_path}")
        return worktree_path

    with RedisLock(
        f"worktree:{github_repo_id}:{commit_sha[:12]}",
        timeout=180,  # Increased for potential replay
        blocking_timeout=60,
    ):
        # Double-check after acquiring lock
        if worktree_path.exists() and (worktree_path / ".git").exists():
            return worktree_path

        # Ensure bare repo exists
        if not repo_path.exists():
            logger.info(f"Bare repo not found, cloning {full_name}")
            clone_bare_repo(github_repo_id, full_name)
            if not repo_path.exists():
                logger.error(f"Failed to clone bare repo for {full_name}")
                return None

        # Ensure commit exists (handles fork commits via replay if needed)
        from app.services.github.github_client import GitHubClient

        github_client = GitHubClient()
        effective_sha = ensure_commit_exists(repo_path, commit_sha, full_name, github_client)

        if not effective_sha:
            logger.warning(f"Commit {commit_sha[:8]} not found and could not be replayed")
            return None

        # Use effective_sha for worktree (may be synthetic commit from replay)
        target_sha = effective_sha

        # Create worktree
        try:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), target_sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=60,
            )
            logger.info(f"Created worktree at {worktree_path} (commit: {target_sha[:8]})")
            return worktree_path
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create worktree: {e.stderr}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("Timeout creating worktree")
            return None


def clone_bare_repo(github_repo_id: int, full_name: str) -> bool:
    """
    Clone repository as bare repo.

    Uses RedisLock to prevent concurrent clones.

    Args:
        github_repo_id: GitHub's internal repository ID
        full_name: Repository full name (owner/repo)

    Returns:
        True if successful, False otherwise
    """
    from app.core.redis import RedisLock

    if not github_repo_id:
        return False

    repo_path = get_repo_path(github_repo_id)

    with RedisLock(f"clone:{github_repo_id}", timeout=700, blocking_timeout=60):
        # Already cloned
        if repo_path.exists():
            return True

        # Build clone URL (with auth if needed)
        clone_url = f"https://github.com/{full_name}.git"

        try:
            from app.services.model_repository_service import is_org_repo

            if is_org_repo(full_name) and settings.GITHUB_INSTALLATION_ID:
                from app.services.github.github_app import get_installation_token

                token = get_installation_token()
                clone_url = f"https://x-access-token:{token}@github.com/{full_name}.git"
        except Exception as e:
            logger.warning(f"Could not get installation token: {e}")

        try:
            logger.info(f"Cloning {full_name} to {repo_path}")
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--bare", clone_url, str(repo_path)],
                check=True,
                capture_output=True,
                timeout=600,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone {full_name}: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout cloning {full_name}")
            return False
