"""
Git Repository Resource Provider.

Handles:
- Cloning repositories
- Fetching updates
- Ensuring commits exist (handling forks)
- Providing git.Repo handle
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from git import Repo

from app.pipeline.resources import ResourceProvider, ResourceNames
from app.utils.locking import repo_lock
from app.services.commit_replay import ensure_commit_exists
from app.services.github.github_app import get_installation_token

if TYPE_CHECKING:
    from app.pipeline.core.context import ExecutionContext

logger = logging.getLogger(__name__)

REPOS_DIR = Path("../repo-data/repos")
REPOS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class GitRepoHandle:
    """Handle to an initialized git repository."""
    repo: Repo
    path: Path
    effective_sha: Optional[str]  # The SHA we're actually working with (may differ from original)
    original_sha: str  # The originally requested SHA
    
    @property
    def is_commit_available(self) -> bool:
        return self.effective_sha is not None


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
    
    def initialize(self, context: "ExecutionContext") -> GitRepoHandle:
        repo = context.repo
        build_sample = context.build_sample
        
        commit_sha = build_sample.tr_original_commit
        if not commit_sha:
            raise ValueError("No commit SHA available in build sample")
        
        repo_path = REPOS_DIR / str(repo.id)
        
        with repo_lock(str(repo.id)):
            # Ensure repo exists
            if not repo_path.exists():
                self._clone_repo(repo, repo_path)
            
            # Fetch latest
            self._run_git(repo_path, ["fetch", "origin"])
            
            # Ensure commit exists (handle forks)
            token = self._get_token(repo, context)
            effective_sha = ensure_commit_exists(
                repo_path, commit_sha, repo.full_name, token
            )
        
        git_repo = Repo(str(repo_path))
        
        return GitRepoHandle(
            repo=git_repo,
            path=repo_path,
            effective_sha=effective_sha,
            original_sha=commit_sha,
        )
    
    def _clone_repo(self, repo, repo_path: Path) -> None:
        """Clone the repository."""
        clone_url = f"https://github.com/{repo.full_name}.git"
        
        # For private repos, use token
        if repo.is_private and repo.installation_id:
            from app.services.github.github_app import get_installation_token
            token = get_installation_token(repo.installation_id)
            clone_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
        
        logger.info(f"Cloning {repo.full_name} to {repo_path}")
        subprocess.run(
            ["git", "clone", "--bare", clone_url, str(repo_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    
    def _run_git(self, cwd: Path, args: list) -> str:
        """Run a git command and return output."""
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    
    def _get_token(self, repo, context: "ExecutionContext") -> Optional[str]:
        """Get GitHub token for API access."""
        if repo.installation_id:
            return get_installation_token(repo.installation_id)
        return None
    
    def cleanup(self, context: "ExecutionContext") -> None:
        # Git repos persist between runs, no cleanup needed
        pass
