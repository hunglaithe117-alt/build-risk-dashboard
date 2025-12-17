import logging
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

import requests
import fcntl

from app.config import settings
from app.paths import SONAR_WORK_DIR
from app.integrations.tools.sonarqube.config import get_sonar_runtime_config

logger = logging.getLogger(__name__)


class SonarCommitRunner:
    def __init__(self, project_key: str):
        self.project_key = project_key
        # Prefer DB-configured settings if available (merged ENV + DB)
        cfg = get_sonar_runtime_config()
        self.host = cfg.host_url
        # If token is empty (masked or not set in DB), fall back to ENV
        self.token = cfg.token or settings.SONAR_TOKEN

        # Use centralized sonar work directory from paths.py
        self.work_dir = SONAR_WORK_DIR / project_key
        self.repo_dir = self.work_dir / "repo"
        self.worktrees_dir = self.work_dir / "worktrees"

        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        self.repo_lock_path = self.work_dir / ".repo.lock"
        self.repo_lock_path.touch(exist_ok=True)

        self.session = requests.Session()
        self.session.auth = (self.token, "")

    def ensure_repo(self, repo_url: str) -> Path:
        if self.repo_dir.exists() and (self.repo_dir / ".git").exists():
            return self.repo_dir
        if self.repo_dir.exists():
            shutil.rmtree(self.repo_dir)

        logger.info(f"Cloning {repo_url} to {self.repo_dir}")
        subprocess.run(
            ["git", "clone", repo_url, str(self.repo_dir)],
            check=True,
            capture_output=True,
        )
        return self.repo_dir

    @contextmanager
    def repo_mutex(self):
        with self.repo_lock_path.open("r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def refresh_repo(self, repo_url: str):
        self.ensure_repo(repo_url)
        subprocess.run(
            ["git", "fetch", "--all", "--tags", "--prune"],
            cwd=self.repo_dir,
            check=False,
            capture_output=True,
        )

    def create_worktree(self, commit_sha: str) -> Path:
        target = self.worktrees_dir / commit_sha
        if target.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(target), "--force"],
                cwd=self.repo_dir,
                check=False,
                capture_output=True,
            )
            shutil.rmtree(target, ignore_errors=True)

        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), commit_sha],
            cwd=self.repo_dir,
            check=True,
            capture_output=True,
        )
        return target

    def remove_worktree(self, commit_sha: str):
        target = self.worktrees_dir / commit_sha
        if target.exists():
            subprocess.run(
                ["git", "worktree", "remove", str(target), "--force"],
                cwd=self.repo_dir,
                check=False,
                capture_output=True,
            )
            shutil.rmtree(target, ignore_errors=True)

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
    ) -> str:
        """
        Run SonarQube scan on a commit.

        Args:
            repo_url: Repository URL (used if shared_worktree_path not provided)
            commit_sha: Commit SHA to scan
            sonar_config_content: Optional custom sonar-project.properties content
            shared_worktree_path: Optional path to shared worktree from pipeline.
                                  If provided, uses this instead of creating own worktree.
        """
        component_key = f"{self.project_key}_{commit_sha}"

        # Check if already exists
        if self._project_exists(component_key):
            logger.info(f"Component {component_key} already exists, skipping scan.")
            return component_key

        # Use shared worktree if provided, otherwise create our own
        use_shared_worktree = shared_worktree_path is not None
        worktree = None

        try:
            if use_shared_worktree:
                # Use shared worktree from pipeline
                worktree = Path(shared_worktree_path)
                if not worktree.exists():
                    raise ValueError(f"Shared worktree path does not exist: {worktree}")
                logger.info(f"Using shared worktree at {worktree} for scan")
            else:
                # Create our own worktree (legacy behavior)
                with self.repo_mutex():
                    self.refresh_repo(repo_url)
                    worktree = self.create_worktree(commit_sha)

            # Write custom config if provided
            if sonar_config_content:
                config_path = worktree / "sonar-project.properties"
                with open(config_path, "w") as f:
                    f.write(sonar_config_content)
                logger.info(
                    f"Wrote custom sonar-project.properties for {component_key}"
                )

            cmd = self.build_scan_command(component_key, worktree)
            logger.info(f"Scanning {component_key}...")

            subprocess.run(
                cmd, cwd=worktree, check=True, capture_output=True, text=True
            )

            return component_key

        except subprocess.CalledProcessError as e:
            logger.error(f"Scan failed: {e.stderr}")
            raise
        finally:
            # Only cleanup if we created our own worktree
            if worktree and not use_shared_worktree:
                with self.repo_mutex():
                    self.remove_worktree(commit_sha)

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
