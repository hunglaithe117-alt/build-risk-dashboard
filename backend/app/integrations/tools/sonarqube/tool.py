"""
SonarQube Integration Tool

Provides code quality analysis via SonarQube.
Uses async scan mode - results are delivered via webhook after scan completes.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.config import settings
from app.integrations.base import (
    IntegrationTool,
    MetricCategory,
    MetricDefinition,
    ToolType,
)
from app.integrations.tools.sonarqube.metrics import SONARQUBE_METRICS
from app.utils.git import ensure_worktree

logger = logging.getLogger(__name__)


class SonarQubeTool(IntegrationTool):
    """
    SonarQube integration for code quality analysis.

    Uses async mode - scans are initiated and results are delivered via webhook.
    Configuration loaded from DB settings (initialized from ENV on first run).
    """

    def __init__(self, project_key: Optional[str] = None, github_repo_id: Optional[int] = None):
        """
        Initialize SonarQube tool.

        Args:
            project_key: SonarQube project key (for scanning)
            github_repo_id: GitHub repo ID (for shared worktree lookup)
        """
        self._metrics = SONARQUBE_METRICS
        self.project_key = project_key
        self.github_repo_id = github_repo_id

        # Load settings from DB
        db_settings = self._get_db_settings()
        self.host = db_settings["host_url"]
        self.token = db_settings["token"]
        self._default_config = db_settings["default_config"]

        self._session: Optional[requests.Session] = None

    def _get_db_settings(self) -> Dict[str, Any]:
        """Load SonarQube settings from database."""
        try:
            from app.database.mongo import get_database
            from app.services.settings_service import SettingsService

            db = get_database()
            service = SettingsService(db)
            app_settings = service.get_settings()

            # Get decrypted token for actual use
            token = service.get_decrypted_token("sonarqube") or ""

            return {
                "host_url": app_settings.sonarqube.host_url.rstrip("/"),
                "token": token,
                "default_config": app_settings.sonarqube.default_config or "",
            }
        except Exception as e:
            logger.warning(f"Could not load SonarQube settings from DB: {e}")

        # Fallback to ENV vars
        return {
            "host_url": settings.SONAR_HOST_URL.rstrip("/"),
            "token": settings.SONAR_TOKEN or "",
            "default_config": "",
        }

    @property
    def session(self) -> requests.Session:
        """Lazy-load requests session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.auth = (self.token, "")
        return self._session

    @property
    def tool_type(self) -> ToolType:
        return ToolType.SONARQUBE

    @property
    def display_name(self) -> str:
        return "SonarQube"

    @property
    def description(self) -> str:
        return "Code quality and security analysis"

    def is_available(self) -> bool:
        """Check if SonarQube is configured and Docker is available."""
        if not self.host or not self.token:
            return False

        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_config(self) -> Dict[str, Any]:
        """Return SonarQube configuration (without secrets)."""
        return {
            "host_url": self.host,
            "has_default_config": bool(self._default_config),
            "configured": self.is_available(),
            "webhook_required": True,
        }

    def get_health_status(self) -> Dict[str, Any]:
        """
        Check SonarQube server health and return detailed status.

        Returns:
            Dict with connected, version, status, etc.
        """
        result = {
            "connected": False,
            "configured": bool(self.host and self.token),
            "host_url": self.host or "",
        }

        if not self.host:
            result["error"] = "Host URL not configured"
            return result

        if not self.token:
            result["error"] = "Token not configured"
            return result

        try:
            # Check server health via system/health API
            health_resp = self.session.get(f"{self.host}/api/system/health", timeout=10)
            if health_resp.status_code == 200:
                health_data = health_resp.json()
                result["connected"] = health_data.get("health") == "GREEN"
                result["status"] = health_data.get("health", "UNKNOWN")
            else:
                # Try system/status as fallback
                status_resp = self.session.get(f"{self.host}/api/system/status", timeout=10)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    result["connected"] = status_data.get("status") == "UP"
                    result["status"] = status_data.get("status", "UNKNOWN")
                    result["version"] = status_data.get("version", "unknown")
                else:
                    result["error"] = f"HTTP {status_resp.status_code}"

        except requests.exceptions.Timeout:
            result["error"] = "Connection timeout"
        except requests.exceptions.ConnectionError:
            result["error"] = "Connection refused"
        except Exception as e:
            result["error"] = str(e)

        return result

    def get_scan_types(self) -> List[str]:
        return ["code_quality", "security", "maintainability", "reliability"]

    def get_metrics(self) -> List[MetricDefinition]:
        return self._metrics

    def get_metric_keys(self) -> List[str]:
        return [m.key for m in self._metrics]

    def get_metrics_by_category(self, category: MetricCategory) -> List[MetricDefinition]:
        return [m for m in self._metrics if m.category == category]

    # =========================================================================
    # Scanning Methods
    # =========================================================================

    def scan_commit(
        self,
        commit_sha: str,
        full_name: str,
        config_file_path: Optional[Path] = None,
        shared_worktree_path: Optional[Path] = None,
    ) -> str:
        """
        Run SonarQube scan on a commit.

        Args:
            commit_sha: Commit SHA to scan
            full_name: Repo full name (owner/repo)
            config_file_path: External config file path (sonar-project.properties)
            shared_worktree_path: Optional path to shared worktree from pipeline

        Returns:
            component_key: SonarQube component key for this scan
        """
        if not self.project_key:
            raise ValueError("project_key is required for scanning")

        component_key = f"{self.project_key}_{commit_sha}"

        # Check if already exists
        if self._project_exists(component_key):
            logger.info(f"Component {component_key} already exists, skipping scan.")
            return component_key

        try:
            # Use provided worktree or ensure one exists
            if shared_worktree_path:
                worktree = Path(shared_worktree_path)
                if not worktree.exists():
                    raise ValueError(f"Shared worktree path does not exist: {worktree}")
            elif self.github_repo_id and full_name:
                worktree = ensure_worktree(self.github_repo_id, commit_sha, full_name)
                if not worktree:
                    raise ValueError(f"Failed to create worktree for {commit_sha}")
            else:
                raise ValueError("Shared worktree path or github_repo_id + full_name required")

            cmd = self._build_scan_command(component_key, worktree, config_file_path)
            logger.info(f"Scanning {component_key}...")

            subprocess.run(cmd, cwd=worktree, check=True, capture_output=True, text=True)

            return component_key

        except subprocess.CalledProcessError as e:
            logger.error(f"Scan failed: {e.stderr}")
            raise

    def fetch_metrics(
        self, component_key: str, selected_metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Fetch metrics from SonarQube API for a given component."""
        from app.integrations.tools.sonarqube.exporter import MetricsExporter

        exporter = MetricsExporter()
        return exporter.collect_metrics(component_key, selected_metrics=selected_metrics)

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _build_scan_command(
        self,
        component_key: str,
        source_dir: Path,
        config_file_path: Optional[Path] = None,
    ) -> List[str]:
        """Build sonar-scanner command using Docker image."""
        scanner_args = [
            f"-Dsonar.projectKey={component_key}",
            f"-Dsonar.projectName={component_key}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={self.host}",
            f"-Dsonar.token={self.token}",
            "-Dsonar.sourceEncoding=UTF-8",
            "-Dsonar.scm.disabled=true",  # Worktrees in Docker don't have valid git refs
            "-Dsonar.java.binaries=.",
        ]

        # Add project.settings if config file provided
        if config_file_path:
            scanner_args.append("-Dproject.settings=/tmp/sonar-project.properties")

        source_dir_str = str(source_dir.absolute())

        docker_args = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{source_dir_str}:/usr/src",
        ]

        # Mount config file if provided
        if config_file_path:
            config_path_str = str(config_file_path.absolute())
            docker_args.extend(["-v", f"{config_path_str}:/tmp/sonar-project.properties:ro"])

        docker_args.extend(
            [
                "-w",
                "/usr/src",
                "--network",
                "host",
                "sonarsource/sonar-scanner-cli:latest",
                *scanner_args,
            ]
        )

        return docker_args

    def _project_exists(self, component_key: str) -> bool:
        """Check if a SonarQube project already exists."""
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
