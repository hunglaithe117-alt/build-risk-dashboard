"""
Trivy Integration Tool

Provides security scanning via Trivy Server mode.
Scans for vulnerabilities, misconfigurations, and secrets.
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.integrations.base import (
    IntegrationTool,
    MetricDefinition,
    ToolType,
)
from app.integrations.tools.trivy.metrics import TRIVY_METRICS
from app.utils.git import ensure_worktree

logger = logging.getLogger(__name__)


class TrivyTool(IntegrationTool):
    """
    Trivy integration for security scanning (Server mode only).

    Uses Trivy server via --server flag for efficient scanning.
    Scans for vulnerabilities, misconfigurations, and secrets.

    Configuration:
    - Connection: server_url from DB settings (required)
    - Scan config: default_config from DB settings (trivy.yaml content)
    """

    def __init__(self, github_repo_id: Optional[int] = None):
        """
        Initialize Trivy tool.

        Args:
            github_repo_id: GitHub repo ID (for shared worktree lookup in scan_commit)
        """
        self._metrics = TRIVY_METRICS
        self.github_repo_id = github_repo_id

        # Load settings from DB
        trivy_settings = self._get_db_settings()
        self._server_url = trivy_settings.get("server_url")
        if not self._server_url:
            raise ValueError("Trivy server URL is required. Configure in settings.")
        self._default_config = trivy_settings.get("default_config", "")
        self._timeout = 600  # Default timeout 10 minutes

    def _get_db_settings(self) -> Dict[str, Any]:
        """Load Trivy settings from database."""
        try:
            from app.database.mongo import get_database
            from app.services.settings_service import SettingsService

            db = get_database()
            service = SettingsService(db)
            app_settings = service.get_settings()

            if app_settings and app_settings.trivy:
                return {
                    "server_url": app_settings.trivy.server_url,
                    "default_config": app_settings.trivy.default_config,
                }
        except Exception as e:
            logger.warning(f"Could not load Trivy settings from DB: {e}")

        # Fallback to env vars
        return {
            "server_url": getattr(settings, "TRIVY_SERVER_URL", None),
            "default_config": "",
        }

    @property
    def tool_type(self) -> ToolType:
        return ToolType.TRIVY

    @property
    def display_name(self) -> str:
        return "Trivy"

    @property
    def description(self) -> str:
        return "Container and dependency vulnerability scanning"

    def is_available(self) -> bool:
        """Check if Trivy Server is available."""
        return self._check_server_health()

    def _check_server_health(self) -> bool:
        """Check if Trivy server is healthy."""
        import requests

        try:
            resp = requests.get(f"{self._server_url}/healthz", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get_config(self) -> Dict[str, Any]:
        """Return Trivy configuration."""
        return {
            "server_url": self._server_url,
            "has_default_config": bool(self._default_config),
            "configured": self.is_available(),
        }

    def get_default_config(self) -> str:
        """Return default trivy.yaml config content from settings."""
        return self._default_config

    def get_health_status(self) -> Dict[str, Any]:
        """
        Check Trivy server health and return detailed status.

        Returns:
            Dict with connected, status, server_url, etc.
        """
        import requests

        result = {
            "connected": False,
            "configured": bool(self._server_url),
            "server_url": self._server_url or "",
        }

        if not self._server_url:
            result["error"] = "Server URL not configured"
            return result

        try:
            resp = requests.get(f"{self._server_url}/healthz", timeout=5)
            if resp.status_code == 200:
                result["connected"] = True
                result["status"] = "healthy"
            else:
                result["error"] = f"Server returned HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            result["error"] = "Server connection timeout"
        except requests.exceptions.ConnectionError:
            result["error"] = "Server connection refused"
        except Exception as e:
            result["error"] = str(e)

        return result

    def get_scan_types(self) -> List[str]:
        """Return supported scan types."""
        return ["vuln", "misconfig", "secret"]

    def get_metrics(self) -> List[MetricDefinition]:
        """Return all metric definitions."""
        return self._metrics

    def get_metric_keys(self) -> List[str]:
        """Return list of metric keys."""
        return [m.key for m in self._metrics]

    def scan(
        self,
        target_path: str,
        scan_types: Optional[List[str]] = None,
        config_file_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Run Trivy security scan on a filesystem path using server mode.

        Args:
            target_path: Path to scan (usually a git worktree)
            scan_types: Types of scans to run (default: ["vuln", "misconfig", "secret"])
            config_file_path: External config file path (trivy.yaml)

        Returns:
            Dict with scan results and metrics
        """
        # Default to all scan types
        if scan_types is None:
            scan_types = ["vuln", "misconfig", "secret"]

        start_time = time.time()

        # Build command
        cmd = self._build_scan_command(
            target_path=target_path,
            scan_types=scan_types,
            config_file_path=config_file_path,
        )

        try:
            logger.info(
                f"Running Trivy scan (server mode) on {target_path} "
                f"with scanners: {scan_types}"
            )
            logger.debug(f"Command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout + 30,  # Extra buffer
            )

            scan_duration_ms = int((time.time() - start_time) * 1000)

            if result.returncode not in (0, 1):
                # returncode 1 means vulnerabilities found (not an error)
                logger.error(f"Trivy scan failed: {result.stderr}")
                return {
                    "error": result.stderr,
                    "status": "failed",
                    "scan_duration_ms": scan_duration_ms,
                }

            # Parse JSON output
            raw_results = json.loads(result.stdout) if result.stdout else {}
            metrics = self._parse_results(raw_results, scan_duration_ms)

            logger.info(
                f"Trivy scan completed: {metrics.get('vuln_total', 0)} vulnerabilities, "
                f"{metrics.get('misconfig_total', 0)} misconfigs in {scan_duration_ms}ms"
            )

            return {
                "status": "success",
                "metrics": metrics,
                "scan_duration_ms": scan_duration_ms,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Trivy scan timed out after {self._timeout}s")
            return {
                "error": "Scan timed out",
                "status": "failed",
                "scan_duration_ms": int((time.time() - start_time) * 1000),
            }
        except FileNotFoundError:
            logger.error("Trivy not found. Please install trivy CLI.")
            return {
                "error": "Trivy not installed",
                "status": "failed",
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Trivy output: {e}")
            return {
                "error": f"JSON parse error: {e}",
                "status": "failed",
            }

    def scan_commit(
        self,
        commit_sha: str,
        full_name: str,
        config_file_path: Optional[Path] = None,
        shared_worktree_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Run Trivy vulnerability scan on a specific commit.

        Creates or uses existing worktree for the commit.

        Args:
            commit_sha: Commit SHA to scan
            full_name: Repo full name (owner/repo)
            config_file_path: Optional trivy.yaml config file path
            shared_worktree_path: Optional path to shared worktree from pipeline

        Returns:
            Dict with scan results and vulnerability metrics
        """

        try:
            if shared_worktree_path:
                worktree = Path(shared_worktree_path)
                if not worktree.exists():
                    return {
                        "error": f"Shared worktree path does not exist: {worktree}",
                        "status": "failed",
                    }
            elif self.github_repo_id and full_name:
                worktree = ensure_worktree(self.github_repo_id, commit_sha, full_name)
                if not worktree:
                    return {
                        "error": f"Failed to create worktree for {commit_sha}",
                        "status": "failed",
                    }
            else:
                return {
                    "error": "Shared worktree path or github_repo_id + full_name required",
                    "status": "failed",
                }

            # Use the regular scan method with the worktree path
            return self.scan(
                target_path=str(worktree),
                config_file_path=config_file_path,
            )

        except Exception as e:
            logger.error(f"scan_commit failed: {e}")
            return {
                "error": str(e),
                "status": "failed",
            }

    def _build_scan_command(
        self,
        target_path: str,
        scan_types: List[str],
        config_file_path: Optional[Path] = None,
    ) -> List[str]:
        """
        Build trivy scan command using Docker image + Trivy server.

        Uses aquasec/trivy Docker image as client connecting to Trivy server.
        Scans for vulnerabilities, misconfigurations, and secrets based on scan_types.
        """
        from pathlib import Path as PathLib

        target_path_abs = str(PathLib(target_path).absolute())

        # Build trivy args - use server mode with specified scan types
        trivy_args = [
            "fs",
            "--format", "json",
            "--timeout", f"{self._timeout}s",
            "--server", self._server_url,
            "--scanners", ",".join(scan_types),  # Use passed scan types
        ]

        # Target path inside container
        trivy_args.append("/work")

        # Build docker command
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{target_path_abs}:/work:ro",  # Mount source as read-only
            "--network", "host",  # Access Trivy server
        ]

        # Mount config file if provided
        if config_file_path:
            config_abs = str(config_file_path.absolute())
            docker_cmd.extend(["-v", f"{config_abs}:/work/trivy.yaml:ro"])
            trivy_args.extend(["--config", "/work/trivy.yaml"])

        # Add image and args
        docker_cmd.append("aquasec/trivy:latest")
        docker_cmd.extend(trivy_args)

        return docker_cmd

    def _parse_results(self, raw_results: Dict[str, Any], scan_duration_ms: int) -> Dict[str, Any]:
        """Parse Trivy JSON output into structured metrics (vuln, misconfig, secret)."""
        vuln_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0,
        }
        misconfig_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0,
        }
        secrets_count = 0
        packages_scanned = 0
        files_scanned = 0

        results = raw_results.get("Results", [])

        for result in results:
            files_scanned += 1

            # Count vulnerabilities
            for vuln in result.get("Vulnerabilities", []):
                severity = vuln.get("Severity", "UNKNOWN").lower()
                if severity in vuln_counts:
                    vuln_counts[severity] += 1
                vuln_counts["total"] += 1
                packages_scanned += 1

            # Count misconfigurations
            for misconf in result.get("Misconfigurations", []):
                severity = misconf.get("Severity", "UNKNOWN").lower()
                if severity in misconfig_counts:
                    misconfig_counts[severity] += 1
                misconfig_counts["total"] += 1

            # Count secrets
            secrets_count += len(result.get("Secrets", []))

        return {
            "vuln_critical": vuln_counts["critical"],
            "vuln_high": vuln_counts["high"],
            "vuln_medium": vuln_counts["medium"],
            "vuln_low": vuln_counts["low"],
            "vuln_total": vuln_counts["total"],
            "misconfig_critical": misconfig_counts["critical"],
            "misconfig_high": misconfig_counts["high"],
            "misconfig_medium": misconfig_counts["medium"],
            "misconfig_low": misconfig_counts["low"],
            "misconfig_total": misconfig_counts["total"],
            "secrets_count": secrets_count,
            "scan_duration_ms": scan_duration_ms,
            "packages_scanned": packages_scanned,
            "files_scanned": files_scanned,
            "has_critical": vuln_counts["critical"] > 0 or misconfig_counts["critical"] > 0,
            "has_high": vuln_counts["high"] > 0 or misconfig_counts["high"] > 0,
        }

    def get_empty_metrics(self) -> Dict[str, Any]:
        """Return dict with all metrics set to default values."""
        return {
            "vuln_critical": 0,
            "vuln_high": 0,
            "vuln_medium": 0,
            "vuln_low": 0,
            "vuln_total": 0,
            "misconfig_critical": 0,
            "misconfig_high": 0,
            "misconfig_medium": 0,
            "misconfig_low": 0,
            "misconfig_total": 0,
            "secrets_count": 0,
            "scan_duration_ms": 0,
            "packages_scanned": 0,
            "files_scanned": 0,
            "has_critical": False,
            "has_high": False,
        }
