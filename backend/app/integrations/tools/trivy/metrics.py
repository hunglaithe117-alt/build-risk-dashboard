"""
Trivy Metrics Definitions

All metrics for Trivy security scanning (vulnerabilities, misconfigurations, secrets).
"""

from typing import List

from app.integrations.base import (
    MetricCategory,
    MetricDataType,
    MetricDefinition,
)

TRIVY_METRICS: List[MetricDefinition] = [
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
    # Secrets Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="secrets_count",
        display_name="Secrets Found",
        description="Number of exposed secrets detected (API keys, passwords, tokens)",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="0",
    ),
    # -------------------------------------------------------------------------
    # Scan Metadata
    # -------------------------------------------------------------------------
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
        display_name="Has Critical Issues",
        description="Whether any critical vulnerabilities or misconfigurations were found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.BOOLEAN,
        example_value="true",
    ),
    MetricDefinition(
        key="has_high",
        display_name="Has High Severity Issues",
        description="Whether any high severity vulnerabilities or misconfigurations were found",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.BOOLEAN,
        example_value="true",
    ),
]

# Backward compatibility alias
TRIVY_VULN_METRICS = TRIVY_METRICS
