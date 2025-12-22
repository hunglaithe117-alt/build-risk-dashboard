"""
Trivy Metrics Definitions

All metric definitions for Trivy vulnerability scanning tool.
"""

from typing import List

from app.integrations.base import (
    MetricCategory,
    MetricDataType,
    MetricDefinition,
)

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
