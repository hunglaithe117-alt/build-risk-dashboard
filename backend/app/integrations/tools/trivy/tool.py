"""
Trivy Integration Tool

Provides vulnerability and security scanning via Trivy.
Supports both standalone CLI mode and server mode (client/server).
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
    Trivy integration for vulnerability scanning.

    Supports two modes:
    - Server mode: Uses Trivy server via --server flag (recommended)
    - Standalone: Runs trivy Docker image directly

    Configuration:
    - Connection: server_url from DB settings
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
        self._default_config = trivy_settings.get("default_config", "")

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
        """Check if Trivy is enabled and Docker is available."""
        # Check Docker is available
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

        # If server URL is configured, also check server health
        if self._server_url:
            return self._check_server_health()

        return True

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
            "server_mode": bool(self._server_url),
            "has_default_config": bool(self._default_config),
            "configured": self.is_available(),
        }

    def get_default_config(self) -> str:
        """Return default trivy.yaml config content from settings."""
        return self._default_config

    def get_scan_types(self) -> List[str]:
        """Return supported scan types."""
        return ["vulnerability", "misconfiguration", "secret", "license"]

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
        config_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run Trivy scan on a filesystem path.

        If TRIVY_SERVER_URL is configured, uses server mode (--server flag).
        Otherwise, runs Trivy CLI directly.

        Args:
            target_path: Path to scan (usually a cloned git repo or worktree)
            scan_types: Types of scans to run (vuln, config, secret, license)
            config_content: Optional trivy.yaml config content

        Returns:
            Dict with scan results and metrics
        """
        if scan_types is None:
            scan_types = ["vuln", "config"]

        start_time = time.time()

        # Use custom config if provided, otherwise use default from settings
        effective_config = config_content or self._default_config
        config_file_path = None
        if effective_config:
            config_file_path = Path(target_path) / "trivy.yaml"
            with open(config_file_path, "w") as f:
                f.write(effective_config)
            logger.info("Wrote trivy.yaml for scan")

        # Build command
        cmd = self._build_scan_command(
            target_path=target_path,
            scan_types=scan_types,
            config_file_path=config_file_path,
        )

        try:
            mode = "server" if self._server_url else "standalone"
            logger.info(f"Running Trivy scan ({mode} mode) on {target_path}")
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
        scan_types: Optional[List[str]] = None,
        config_content: Optional[str] = None,
        shared_worktree_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Run Trivy scan on a specific commit.

        Creates or uses existing worktree for the commit.

        Args:
            commit_sha: Commit SHA to scan
            full_name: Repo full name (owner/repo)
            scan_types: Types of scans to run
            config_content: Optional trivy.yaml config content
            shared_worktree_path: Optional path to shared worktree from pipeline

        Returns:
            Dict with scan results and metrics
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
                scan_types=scan_types,
                config_content=config_content,
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
        Build trivy scan command using Docker image.

        Uses aquasec/trivy Docker image. Requires Docker to be installed.
        If TRIVY_SERVER_URL is configured, connects to Trivy server.
        """
        from pathlib import Path as PathLib

        target_path_abs = str(PathLib(target_path).absolute())

        # Build trivy args
        trivy_args = [
            "fs",
            "--format",
            "json",
            "--severity",
            self._severity,
            "--timeout",
            f"{self._timeout}s",
        ]

        # Add server flag if configured (client/server mode)
        if self._server_url:
            trivy_args.extend(["--server", self._server_url])

        # Add skip dirs
        if self._skip_dirs:
            for skip_dir in self._skip_dirs.split(","):
                trivy_args.extend(["--skip-dirs", skip_dir.strip()])

        # Add scan types
        trivy_args.extend(["--scanners", ",".join(scan_types)])

        # Target path inside container
        trivy_args.append("/work")

        # Build docker command
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{target_path_abs}:/work:ro",  # Mount as read-only
        ]

        # Mount config file if provided
        if config_file_path:
            config_abs = str(config_file_path.absolute())
            docker_cmd.extend(["-v", f"{config_abs}:/work/trivy.yaml:ro"])
            trivy_args.extend(["--config", "/work/trivy.yaml"])

        # Use host network to access Trivy server via localhost
        docker_cmd.extend(["--network", "host"])

        # Add trivy cache volume for DB
        docker_cmd.extend(["-v", "trivy_cache:/root/.cache/trivy"])

        # Add image and args
        docker_cmd.append("aquasec/trivy:latest")
        docker_cmd.extend(trivy_args)

        return docker_cmd

    def _parse_results(self, raw_results: Dict[str, Any], scan_duration_ms: int) -> Dict[str, Any]:
        """Parse Trivy JSON output into structured metrics."""
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
        top_vulnerable_packages = []

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

                # Track top vulnerable packages
                pkg_name = vuln.get("PkgName", "unknown")
                if len(top_vulnerable_packages) < 10:
                    top_vulnerable_packages.append(
                        {
                            "name": pkg_name,
                            "severity": severity,
                            "vulnerability_id": vuln.get("VulnerabilityID", ""),
                            "title": vuln.get("Title", ""),
                        }
                    )

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
            "has_critical": vuln_counts["critical"] > 0,
            "has_high": vuln_counts["high"] > 0,
            "top_vulnerable_packages": top_vulnerable_packages,
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
            "top_vulnerable_packages": [],
        }
