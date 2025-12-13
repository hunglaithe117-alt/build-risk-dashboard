"""
Trivy Integration Tool

Provides vulnerability and security scanning via Trivy.
Uses sync mode - results are returned directly after scan completes.
"""

import subprocess
import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.integrations.base import (
    IntegrationTool,
    ToolType,
    ScanMode,
    MetricDefinition,
    MetricCategory,
    MetricDataType,
)
from app.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# TRIVY METRICS DEFINITIONS
# =============================================================================
# Preserved from pipeline/feature_metadata/trivy.py

TRIVY_METRICS: List[MetricDefinition] = [
    # -------------------------------------------------------------------------
    # Vulnerability Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="vuln_critical",
        display_name="Critical Vulnerabilities",
        description="Number of critical severity vulnerabilities found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="2",
    ),
    MetricDefinition(
        key="vuln_high",
        display_name="High Vulnerabilities",
        description="Number of high severity vulnerabilities found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="5",
    ),
    MetricDefinition(
        key="vuln_medium",
        display_name="Medium Vulnerabilities",
        description="Number of medium severity vulnerabilities found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="12",
    ),
    MetricDefinition(
        key="vuln_low",
        display_name="Low Vulnerabilities",
        description="Number of low severity vulnerabilities found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="8",
    ),
    MetricDefinition(
        key="vuln_total",
        display_name="Total Vulnerabilities",
        description="Total number of vulnerabilities found across all severity levels",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="27",
    ),
    # -------------------------------------------------------------------------
    # Misconfiguration Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="misconfig_critical",
        display_name="Critical Misconfigurations",
        description="Number of critical IaC misconfigurations (Terraform, Kubernetes, etc.)",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="1",
    ),
    MetricDefinition(
        key="misconfig_high",
        display_name="High Misconfigurations",
        description="Number of high severity IaC misconfigurations",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="3",
    ),
    MetricDefinition(
        key="misconfig_medium",
        display_name="Medium Misconfigurations",
        description="Number of medium severity IaC misconfigurations",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="7",
    ),
    MetricDefinition(
        key="misconfig_low",
        display_name="Low Misconfigurations",
        description="Number of low severity IaC misconfigurations",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="4",
    ),
    MetricDefinition(
        key="misconfig_total",
        display_name="Total Misconfigurations",
        description="Total number of IaC misconfigurations found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="15",
    ),
    # -------------------------------------------------------------------------
    # Other Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="secrets_count",
        display_name="Secrets Found",
        description="Number of exposed secrets detected (API keys, passwords, tokens)",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="0",
    ),
    MetricDefinition(
        key="scan_duration_ms",
        display_name="Scan Duration",
        description="Time taken to complete Trivy scan",
        category=MetricCategory.METADATA,
        data_type=MetricDataType.INTEGER,
        example_value="2340",
        unit="ms",
    ),
    MetricDefinition(
        key="packages_scanned",
        display_name="Packages Scanned",
        description="Number of packages analyzed for vulnerabilities",
        category=MetricCategory.METADATA,
        data_type=MetricDataType.INTEGER,
        example_value="156",
    ),
    MetricDefinition(
        key="files_scanned",
        display_name="Files Scanned",
        description="Number of files analyzed for security issues",
        category=MetricCategory.METADATA,
        data_type=MetricDataType.INTEGER,
        example_value="42",
    ),
    MetricDefinition(
        key="has_critical",
        display_name="Has Critical Vulnerabilities",
        description="Whether any critical vulnerabilities were found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.BOOLEAN,
        example_value="true",
    ),
    MetricDefinition(
        key="has_high",
        display_name="Has High Vulnerabilities",
        description="Whether any high severity vulnerabilities were found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.BOOLEAN,
        example_value="true",
    ),
    MetricDefinition(
        key="top_vulnerable_packages",
        display_name="Top Vulnerable Packages",
        description="List of top 10 vulnerable packages with severity and CVE details",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.JSON,
        nullable=True,
        example_value='[{"name": "lodash", "severity": "high", "cve": "CVE-2021-23337"}]',
    ),
]


class TrivyTool(IntegrationTool):
    """
    Trivy integration for vulnerability scanning.

    Uses sync mode - scans are executed and results returned directly.
    """

    def __init__(self):
        self._metrics = TRIVY_METRICS
        self._severity = getattr(settings, "TRIVY_SEVERITY", "CRITICAL,HIGH,MEDIUM")
        self._timeout = getattr(settings, "TRIVY_TIMEOUT", 300)
        self._skip_dirs = getattr(
            settings, "TRIVY_SKIP_DIRS", "node_modules,vendor,.git"
        )

    @property
    def tool_type(self) -> ToolType:
        return ToolType.TRIVY

    @property
    def display_name(self) -> str:
        return "Trivy"

    @property
    def description(self) -> str:
        return "Container and dependency vulnerability scanning"

    @property
    def scan_mode(self) -> ScanMode:
        return ScanMode.SYNC  # Results returned directly

    def is_available(self) -> bool:
        """Check if Trivy is enabled and the binary is accessible."""
        if not getattr(settings, "TRIVY_ENABLED", False):
            return False

        try:
            result = subprocess.run(
                ["trivy", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_config(self) -> Dict[str, Any]:
        """Return Trivy configuration."""
        return {
            "enabled": getattr(settings, "TRIVY_ENABLED", False),
            "severity": self._severity,
            "timeout": self._timeout,
            "skip_dirs": self._skip_dirs,
            "configured": self.is_available(),
        }

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
    ) -> Dict[str, Any]:
        """
        Run Trivy scan on a filesystem path.

        Args:
            target_path: Path to scan (usually a cloned git repo or worktree)
            scan_types: Types of scans to run (vuln, config, secret, license)

        Returns:
            Dict with scan results and metrics
        """
        if scan_types is None:
            scan_types = ["vuln", "config"]

        start_time = time.time()

        cmd = [
            "trivy",
            "fs",
            "--format",
            "json",
            "--severity",
            self._severity,
            "--timeout",
            f"{self._timeout}s",
        ]

        # Add skip dirs
        if self._skip_dirs:
            for skip_dir in self._skip_dirs.split(","):
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
            logger.error("Trivy not found. Please install trivy.")
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

    def _parse_results(
        self, raw_results: Dict[str, Any], scan_duration_ms: int
    ) -> Dict[str, Any]:
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
