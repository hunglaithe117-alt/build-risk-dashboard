"""
Git Repository Resource Provider.

Handles:
- Cloning repositories
- Fetching updates
- Ensuring commits exist (handling forks)
- Providing git.Repo handle
"""

from __future__ import annotations
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from git import Repo

from app.pipeline.resources import ResourceProvider, ResourceNames
from app.utils.locking import repo_lock
from app.services.commit_replay import ensure_commit_exists
from app.services.github.github_app import get_installation_token
from app.pipeline.core.context import ExecutionContext

logger = logging.getLogger(__name__)

REPOS_DIR = Path("../repo-data/repos")
REPOS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class GitRepoHandle:
    """Handle to an initialized git repository with shared worktree."""

    repo: Repo
    path: Path
    worktree_path: Optional[Path]
    effective_sha: Optional[str]
    original_sha: str
    is_missing_commit: bool = False

    @property
    def is_commit_available(self) -> bool:
        return self.effective_sha is not None

    @property
    def has_worktree(self) -> bool:
        return self.worktree_path is not None and self.worktree_path.exists()


class GitRepoProvider(ResourceProvider):
    """
    Provides access to a cloned git repository.

    Handles:
    - Cloning if needed
    - Fetching latest
    - Ensuring the target commit exists (handles fork PRs)
    """

    @property
    def name(self) -> str:
        return ResourceNames.GIT_REPO

    def initialize(self, context: ExecutionContext) -> GitRepoHandle:
        repo = context.repo
        workflow_run = context.workflow_run

        commit_sha = workflow_run.head_sha if workflow_run else None
        if not commit_sha:
            raise ValueError("No commit SHA available in workflow run")

        repo_path = REPOS_DIR / str(repo.id)

        with repo_lock(str(repo.id)):
            # Ensure repo exists
            if not repo_path.exists():
                self._clone_repo(repo, repo_path)

            # Fetch latest
            self._run_git(repo_path, ["fetch", "origin"])

            # Ensure commit exists (handle forks)
            token = self._get_token(repo, context)

            # Get GitHubClient if available for better API handling
            github_client = None
            if context.has_resource(ResourceNames.GITHUB_CLIENT):
                github_client = context.get_resource(ResourceNames.GITHUB_CLIENT)

            effective_sha = ensure_commit_exists(
                repo_path=repo_path,
                commit_sha=commit_sha,
                repo_slug=repo.full_name,
                token=token,
                github_client=github_client,
            )

            is_missing_commit = effective_sha is None
            if is_missing_commit:
                logger.warning(
                    f"Commit {commit_sha} not found and could not be replayed "
                    f"(likely a fork commit that exceeded max traversal depth)"
                )

            # Pre-fetch blobs for the commit (important for partial clones)
            # This avoids slow lazy fetch when running `git worktree add` later
            if effective_sha:
                self._prefetch_commit_blobs(repo_path, effective_sha)

            # Create shared worktree at the commit
            worktree_path = self._create_shared_worktree(repo_path, effective_sha)

        git_repo = Repo(str(repo_path))

        return GitRepoHandle(
            repo=git_repo,
            path=repo_path,
            worktree_path=worktree_path,
            effective_sha=effective_sha,
            original_sha=commit_sha,
            is_missing_commit=is_missing_commit,
        )

    def _clone_repo(self, repo, repo_path: Path, max_retries: int = 2) -> None:
        """
        Clone the repository using partial clone for faster initial download.

        Uses --filter=blob:none to skip downloading file blobs during clone.
        Blobs are fetched on-demand when needed (e.g., when checking out files).
        This can reduce clone time from 5+ minutes to under 1 minute for large repos.
        """
        clone_url = f"https://github.com/{repo.full_name}.git"

        # For private repos, use token
        if repo.is_private and repo.installation_id:
            from app.services.github.github_app import get_installation_token

            token = get_installation_token(repo.installation_id)
            clone_url = (
                f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
            )

        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    f"Cloning {repo.full_name} to {repo_path} (attempt {attempt + 1})"
                )

                # Use partial clone to skip blobs initially
                # This dramatically speeds up initial clone for large repos
                clone_cmd = [
                    "git",
                    "clone",
                    "--bare",
                    "--filter=blob:none",
                    clone_url,
                    str(repo_path),
                ]

                subprocess.run(
                    clone_cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )

                logger.info(f"Successfully cloned {repo.full_name}")
                return

            except subprocess.TimeoutExpired as e:
                logger.warning(
                    f"Clone attempt {attempt + 1} timed out for {repo.full_name}"
                )
                # Clean up partial clone if exists
                if repo_path.exists():
                    import shutil

                    shutil.rmtree(repo_path, ignore_errors=True)

                if attempt == max_retries:
                    raise RuntimeError(
                        f"Clone timed out after {max_retries + 1} attempts for {repo.full_name}"
                    ) from e

            except subprocess.CalledProcessError as e:
                logger.error(
                    f"Clone failed for {repo.full_name}: {e.stderr or e.stdout}"
                )
                # Clean up failed clone
                if repo_path.exists():
                    import shutil

                    shutil.rmtree(repo_path, ignore_errors=True)

                if attempt == max_retries:
                    raise

    def _run_git(self, cwd: Path, args: list, timeout: int = 120) -> str:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        return result.stdout.strip()

    def _prefetch_commit_blobs(self, repo_path: Path, sha: str) -> None:
        """
        Pre-fetch blobs for a specific commit.

        For partial clones (--filter=blob:none), blobs are fetched lazily.
        This method pre-fetches the tree and blobs for a commit, so that
        `git worktree add` runs instantly without network calls.

        Uses `git rev-list --objects` + `git fetch-pack` to fetch only
        objects needed for this specific commit's tree.
        """
        try:
            # Fetch the commit's tree and all reachable blobs
            # This is much faster than checking out all files individually
            logger.debug(f"Pre-fetching blobs for commit {sha[:8]}...")

            # Use git cat-file to trigger lazy fetch of the tree
            # This will fetch the tree structure (not all blobs yet)
            subprocess.run(
                ["git", "rev-parse", "--verify", f"{sha}^{{tree}}"],
                cwd=str(repo_path),
                capture_output=True,
                check=True,
                timeout=60,
            )

            # Fetch blobs by listing objects and fetching missing ones
            # Using --missing=allow-any to handle partial clone gracefully
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    "fetch.negotiationAlgorithm=noop",
                    "fetch",
                    "origin",
                    sha,
                    "--no-tags",
                    "--depth=1",
                ],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for blob fetch
            )

            if result.returncode == 0:
                logger.debug(f"Pre-fetched blobs for commit {sha[:8]}")
            else:
                # Not critical - worktree will lazy fetch if needed
                logger.debug(
                    f"Blob pre-fetch returned non-zero for {sha[:8]}: {result.stderr}"
                )

        except subprocess.TimeoutExpired:
            logger.warning(f"Blob pre-fetch timed out for {sha[:8]}, will lazy fetch")
        except Exception as e:
            # Not critical - git will lazy fetch when needed
            logger.debug(f"Blob pre-fetch failed for {sha[:8]}: {e}")

    def _get_token(self, repo, context: "ExecutionContext") -> Optional[str]:
        """Get GitHub token for API access."""
        if repo.installation_id:
            return get_installation_token(repo.installation_id)
        return None

    def _create_shared_worktree(
        self, repo_path: Path, commit_sha: str
    ) -> Optional[Path]:
        """
        Create a shared worktree at the commit for all feature nodes to use.
        Worktrees are stored in: repo-data/worktrees/{repo_id}/{commit_sha}
        """
        if not commit_sha:
            return None

        worktree_base = (
            repo_path.parent.parent / "worktrees" / repo_path.name
        ).resolve()
        worktree_base.mkdir(parents=True, exist_ok=True)
        worktree_path = worktree_base / commit_sha

        try:
            # If worktree already exists and is valid, reuse it
            git_marker = worktree_path / ".git"
            if worktree_path.exists() and git_marker.exists():
                logger.info(
                    f"Reusing existing worktree at {worktree_path} for commit {commit_sha[:8]}"
                )
                return worktree_path

            # Remove existing worktree from git's tracking (handles both registered and on-disk cases)
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=str(repo_path),
                capture_output=True,
                check=False,
                timeout=30,
            )

            # Also remove directory if it exists but has no .git marker
            if worktree_path.exists():
                import shutil

                logger.info(f"Cleaning up incomplete worktree at {worktree_path}")
                shutil.rmtree(worktree_path, ignore_errors=True)

            # Prune any remaining stale references
            subprocess.run(
                ["git", "worktree", "prune"],
                cwd=str(repo_path),
                capture_output=True,
                check=False,
                timeout=30,
            )

            # Create new worktree at the commit
            result = subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), commit_sha],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=180,
            )

            if result.returncode != 0:
                logger.error(f"Failed to create shared worktree: {result.stderr}")
                return None

            logger.info(
                f"Created shared worktree at {worktree_path} for commit {commit_sha[:8]}"
            )
            return worktree_path

        except Exception as e:
            logger.error(f"Error creating shared worktree: {e}")
            return None
