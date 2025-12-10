"""
Trivy Data Source - Container and IaC vulnerability scanning.

Features provided:
- Vulnerability counts by severity
- Package vulnerability details
- IaC misconfigurations
"""

from typing import List, Set

from app.pipeline.sources import (
    DataSource,
    DataSourceConfig,
    DataSourceMetadata,
    DataSourceType,
    register_data_source,
)
from app.pipeline.core.context import ExecutionContext


@register_data_source(DataSourceType.TRIVY)
class TrivyDataSource(DataSource):
    """
    Trivy security scanner data source.

    Runs Trivy against the repository at the build commit
    to detect vulnerabilities in containers, IaC, and dependencies.

    Requirements:
    - Trivy must be installed on the worker node
    - Repository must be cloned (requires git_repo resource)
    """

    @classmethod
    def get_metadata(cls) -> DataSourceMetadata:
        return DataSourceMetadata(
            source_type=DataSourceType.TRIVY,
            display_name="Trivy Scanner",
            description="Scan for container, IaC, and dependency vulnerabilities using Trivy",
            icon="shield-alert",
            requires_config=True,
            config_fields=[
                {
                    "name": "scan_types",
                    "type": "multiselect",
                    "label": "Scan Types",
                    "description": "Types of scans to run",
                    "options": [
                        {"value": "vuln", "label": "Vulnerabilities"},
                        {"value": "config", "label": "Misconfigurations"},
                        {"value": "secret", "label": "Secrets"},
                        {"value": "license", "label": "Licenses"},
                    ],
                    "default": ["vuln", "config"],
                },
                {
                    "name": "severity",
                    "type": "multiselect",
                    "label": "Minimum Severity",
                    "description": "Minimum severity level to report",
                    "options": [
                        {"value": "CRITICAL", "label": "Critical"},
                        {"value": "HIGH", "label": "High"},
                        {"value": "MEDIUM", "label": "Medium"},
                        {"value": "LOW", "label": "Low"},
                    ],
                    "default": ["CRITICAL", "HIGH", "MEDIUM"],
                },
                {
                    "name": "skip_dirs",
                    "type": "string",
                    "label": "Skip Directories",
                    "description": "Comma-separated list of directories to skip",
                    "placeholder": "node_modules,vendor,.git",
                    "required": False,
                },
                {
                    "name": "timeout",
                    "type": "number",
                    "label": "Timeout (seconds)",
                    "description": "Maximum time to run scan",
                    "default": 300,
                },
            ],
            features_provided=cls.get_feature_names(),
            resource_dependencies={"git_repo"},  # Needs cloned repo
        )

    @classmethod
    def get_feature_names(cls) -> Set[str]:
        """Features provided by Trivy scans."""
        return {
            # Vulnerability counts by severity
            "trivy_vuln_critical",
            "trivy_vuln_high",
            "trivy_vuln_medium",
            "trivy_vuln_low",
            "trivy_vuln_total",
            # Misconfiguration counts
            "trivy_misconfig_critical",
            "trivy_misconfig_high",
            "trivy_misconfig_medium",
            "trivy_misconfig_low",
            "trivy_misconfig_total",
            # Secret detection
            "trivy_secrets_count",
            "trivy_secrets_types",
            # License issues
            "trivy_license_issues",
            # Aggregated metrics
            "trivy_scan_duration_ms",
            "trivy_packages_scanned",
            "trivy_files_scanned",
            "trivy_has_critical",
            "trivy_has_high",
            # Top vulnerable packages
            "trivy_top_vulnerable_packages",
        }

    @classmethod
    def get_required_resources(cls) -> Set[str]:
        return {"git_repo"}

    @classmethod
    def is_available(cls, context: ExecutionContext) -> bool:
        # Check if git repo is available (needed to scan)
        return context.has_resource("git_repo")

    @classmethod
    def validate_config(cls, config: DataSourceConfig) -> List[str]:
        errors = []

        # Validate scan types
        allowed_types = {"vuln", "config", "secret", "license"}
        scan_types = config.options.get("scan_types", [])
        if scan_types:
            invalid_types = set(scan_types) - allowed_types
            if invalid_types:
                errors.append(f"Invalid scan types: {invalid_types}")

        # Validate timeout
        timeout = config.options.get("timeout", 300)
        if timeout < 30 or timeout > 3600:
            errors.append("Timeout must be between 30 and 3600 seconds")

        return errors
