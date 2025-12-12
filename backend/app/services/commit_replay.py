from __future__ import annotations
from app.services.github.github_client import GitHubClient

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.services.github.github_client import get_public_github_client

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
        pass

    logger.info(
        f"Direct fetch failed. Attempting to replay fork commit {commit_sha}..."
    )

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
    commit_exists: callable,
    github_client: GitHubClient,
    max_depth: int = 50,
) -> ReplayPlan:
    """
    Constructs a plan to replay missing commits by traversing up ancestry
    until a locally existing commit is found.
    """
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
            raise MissingForkCommitError(current, f"GitHub API error: {e}")

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
            raise MissingForkCommitError(current, f"Failed to download patch: {e}")

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
    import shutil
    import os

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
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to apply patch for {commit.sha}: {e.stderr}"
                )

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
                )
            except subprocess.CalledProcessError:
                # Try with --allow-empty if no changes
                subprocess.run(
                    ["git", "commit", "-m", commit.message, "--allow-empty"],
                    cwd=str(replay_worktree),
                    env=env,
                    check=True,
                    capture_output=True,
                )

            # Get the new SHA
            last_sha = _run_git(replay_worktree, ["rev-parse", "HEAD"])

        logger.info(
            f"Replay complete. Synthetic commit: {last_sha} (from {target_sha})"
        )
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
