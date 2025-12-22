import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional

import requests

from app.config import settings
from app.core.redis import RedisLock
from app.integrations.tools.sonarqube.config import get_sonar_runtime_config
from app.paths import REPOS_DIR, WORKTREES_DIR

logger = logging.getLogger(__name__)


class SonarCommitRunner:
    """
    SonarQube scanner that uses shared repo/worktree infrastructure.

    Now uses:
    - REPOS_DIR for bare repos (shared with ingestion_tasks)
    - WORKTREES_DIR for worktrees (shared with ingestion_tasks)
    - RedisLock for concurrency control
    """

    def __init__(self, project_key: str, raw_repo_id: Optional[str] = None):
        self.project_key = project_key
        self.raw_repo_id = raw_repo_id  # For shared worktree lookup

        # Prefer DB-configured settings if available (merged ENV + DB)
        cfg = get_sonar_runtime_config()
        self.host = cfg.host_url
        # If token is empty (masked or not set in DB), fall back to ENV
        self.token = cfg.token or settings.SONAR_TOKEN

        self.session = requests.Session()
        self.session.auth = (self.token, "")

    def _get_repo_path(self) -> Optional[Path]:
        """Get path to bare repo in shared REPOS_DIR."""
        if not self.raw_repo_id:
            return None
        return REPOS_DIR / self.raw_repo_id

    def _get_worktree_path(self, commit_sha: str) -> Optional[Path]:
        """Get path to worktree in shared WORKTREES_DIR."""
        if not self.raw_repo_id:
            return None
        return WORKTREES_DIR / self.raw_repo_id / commit_sha[:12]

    def ensure_shared_worktree(self, commit_sha: str, full_name: str) -> Optional[Path]:
        """
        Ensure worktree exists using shared infrastructure.

        Uses RedisLock to coordinate with ingestion_tasks and integration_scan.
        """
        if not self.raw_repo_id:
            logger.warning("No raw_repo_id set, cannot use shared worktree")
            return None

        worktree_path = self._get_worktree_path(commit_sha)
        repo_path = self._get_repo_path()

        # Quick check
        if worktree_path.exists() and (worktree_path / ".git").exists():
            logger.info(f"Using existing shared worktree: {worktree_path}")
            return worktree_path

        with RedisLock(
            f"worktree:{self.raw_repo_id}:{commit_sha[:12]}",
            timeout=120,
            blocking_timeout=60,
        ):
            # Double-check after lock
            if worktree_path.exists() and (worktree_path / ".git").exists():
                return worktree_path

            # Check if bare repo exists
            if not repo_path or not repo_path.exists():
                logger.warning(f"Bare repo not found at {repo_path}")
                # Try to clone it
                self._clone_bare_repo(full_name)
                if not repo_path.exists():
                    return None

            # Verify commit exists
            result = subprocess.run(
                ["git", "cat-file", "-e", commit_sha],
                cwd=str(repo_path),
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(f"Commit {commit_sha[:8]} not found in repo")
                return None

            # Create worktree
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_path), commit_sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=60,
            )
            logger.info(f"Created shared worktree: {worktree_path}")
            return worktree_path

    def _clone_bare_repo(self, full_name: str) -> None:
        """Clone repo as bare using shared infrastructure."""
        if not self.raw_repo_id:
            return

        repo_path = self._get_repo_path()

        with RedisLock(f"clone:{self.raw_repo_id}", timeout=700, blocking_timeout=60):
            if repo_path.exists():
                return

            from app.services.model_repository_service import is_org_repo

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

    def build_scan_command(self, component_key: str, source_dir: Path) -> List[str]:
        scanner_args = [
            f"-Dsonar.projectKey={component_key}",
            f"-Dsonar.projectName={component_key}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={self.host}",
            f"-Dsonar.token={self.token}",
            "-Dsonar.sourceEncoding=UTF-8",
            "-Dsonar.scm.exclusions.disabled=true",
            "-Dsonar.java.binaries=.",
        ]

        scanner_exe = os.environ.get("SONAR_SCANNER_HOME", "")
        if scanner_exe:
            scanner_exe = os.path.join(scanner_exe, "bin", "sonar-scanner")
        else:
            scanner_exe = "sonar-scanner"

        return [scanner_exe, *scanner_args]

    def scan_commit(
        self,
        repo_url: str,
        commit_sha: str,
        sonar_config_content: Optional[str] = None,
        shared_worktree_path: Optional[Path] = None,
        full_name: Optional[str] = None,
    ) -> str:
        """
        Run SonarQube scan on a commit.

        Args:
            repo_url: Repository URL (used for extracting full_name if not provided)
            commit_sha: Commit SHA to scan
            sonar_config_content: Optional custom sonar-project.properties content
            shared_worktree_path: Optional path to shared worktree from pipeline.
            full_name: Optional repo full name (e.g., "owner/repo")
        """
        component_key = f"{self.project_key}_{commit_sha}"

        # Check if already exists
        if self._project_exists(component_key):
            logger.info(f"Component {component_key} already exists, skipping scan.")
            return component_key

        # Extract full_name from repo_url if not provided
        if not full_name and repo_url:
            # Parse "https://github.com/owner/repo.git" -> "owner/repo"
            full_name = repo_url.replace("https://github.com/", "").replace(".git", "")

        worktree = None

        try:
            if shared_worktree_path:
                # Use provided shared worktree
                worktree = Path(shared_worktree_path)
                if not worktree.exists():
                    raise ValueError(f"Shared worktree path does not exist: {worktree}")
                logger.info(f"Using provided shared worktree at {worktree} for scan")
            elif self.raw_repo_id and full_name:
                # Use shared worktree infrastructure
                worktree = self.ensure_shared_worktree(commit_sha, full_name)
                if not worktree:
                    raise ValueError(f"Failed to create shared worktree for {commit_sha}")
                logger.info(f"Using shared worktree at {worktree} for scan")
            else:
                raise ValueError("Either shared_worktree_path or raw_repo_id + full_name required")

            # Write custom config if provided
            if sonar_config_content:
                config_path = worktree / "sonar-project.properties"
                with open(config_path, "w") as f:
                    f.write(sonar_config_content)
                logger.info(f"Wrote custom sonar-project.properties for {component_key}")

            cmd = self.build_scan_command(component_key, worktree)
            logger.info(f"Scanning {component_key}...")

            subprocess.run(cmd, cwd=worktree, check=True, capture_output=True, text=True)

            return component_key

        except subprocess.CalledProcessError as e:
            logger.error(f"Scan failed: {e.stderr}")
            raise

    def _project_exists(self, component_key: str) -> bool:
        url = f"{self.host}/api/projects/search"
        try:
            resp = self.session.get(url, params={"projects": component_key}, timeout=10)
            if resp.status_code != 200:
                return False
            data = resp.json()
            components = data.get("components") or []
            return any(comp.get("key") == component_key for comp in components)
        except Exception:
            return False
