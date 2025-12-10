"""
Trivy Resource Provider - Container/IaC vulnerability scanning.

Runs Trivy against cloned repositories to detect vulnerabilities.
"""

import subprocess
import json
import logging
from typing import Any, Dict, Optional

from app.pipeline.resources import ResourceProvider
from app.pipeline.core.context import ExecutionContext
from app.config import settings

logger = logging.getLogger(__name__)


class TrivyClient:
    """
    Client for running Trivy scans.

    Can run locally via CLI or connect to a Trivy server.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        severity: str = "CRITICAL,HIGH,MEDIUM",
        timeout: int = 300,
        skip_dirs: Optional[str] = None,
    ):
        self.server_url = server_url
        self.severity = severity
        self.timeout = timeout
        self.skip_dirs = skip_dirs or "node_modules,vendor,.git"

    def scan_filesystem(
        self,
        target_path: str,
        scan_types: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Scan a filesystem path for vulnerabilities.

        Args:
            target_path: Path to scan (usually a cloned git repo)
            scan_types: Types of scans (vuln, config, secret, license)

        Returns:
            Dict with vulnerability counts and details
        """
        if scan_types is None:
            scan_types = ["vuln", "config"]

        cmd = [
            "trivy",
            "fs",
            "--format",
            "json",
            "--severity",
            self.severity,
            "--timeout",
            f"{self.timeout}s",
        ]

        # Add server URL if configured
        if self.server_url:
            cmd.extend(["--server", self.server_url])

        # Add skip dirs
        if self.skip_dirs:
            for skip_dir in self.skip_dirs.split(","):
                cmd.extend(["--skip-dirs", skip_dir.strip()])

        # Add scan types
        cmd.extend(["--scanners", ",".join(scan_types)])

        # Add target path
        cmd.append(target_path)

        try:
            logger.info(f"Running Trivy scan on {target_path}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 30,  # Extra buffer
            )

            if result.returncode != 0 and result.returncode != 1:
                # returncode 1 means vulnerabilities found (not an error)
                logger.error(f"Trivy scan failed: {result.stderr}")
                return {"error": result.stderr, "results": []}

            # Parse JSON output
            scan_results = json.loads(result.stdout) if result.stdout else {}
            return self._parse_results(scan_results)

        except subprocess.TimeoutExpired:
            logger.error(f"Trivy scan timed out after {self.timeout}s")
            return {"error": "Scan timed out", "results": []}
        except FileNotFoundError:
            logger.error("Trivy not found. Please install trivy or use server mode.")
            return {"error": "Trivy not installed", "results": []}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Trivy output: {e}")
            return {"error": f"JSON parse error: {e}", "results": []}

    def _parse_results(self, raw_results: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Trivy JSON output into structured results."""
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
            target = result.get("Target", "")
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
            "packages_scanned": packages_scanned,
            "files_scanned": files_scanned,
            "has_critical": vuln_counts["critical"] > 0,
            "has_high": vuln_counts["high"] > 0,
            "top_vulnerable_packages": top_vulnerable_packages,
        }

    def is_available(self) -> bool:
        """Check if Trivy is available."""
        try:
            result = subprocess.run(
                ["trivy", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


class TrivyResourceProvider(ResourceProvider):
    """Resource provider for Trivy vulnerability scanner."""

    @property
    def name(self) -> str:
        return "trivy_client"

    def initialize(self, context: ExecutionContext) -> TrivyClient:
        """Initialize Trivy client."""
        # Get server URL from env if Trivy server is running
        server_url = None
        if settings.TRIVY_ENABLED:
            # Check if we should use server mode
            # Default to localhost:4954 if running via docker-compose
            server_url = "http://trivy:4954"  # Docker service name

        return TrivyClient(
            server_url=server_url,
            severity=settings.TRIVY_SEVERITY,
            timeout=settings.TRIVY_TIMEOUT,
            skip_dirs=settings.TRIVY_SKIP_DIRS,
        )


# Register provider for import
trivy_provider = TrivyResourceProvider()
