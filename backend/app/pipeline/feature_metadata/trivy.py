from app.pipeline.core.registry import (
    FeatureMetadata,
    FeatureCategory,
    FeatureDataType,
    FeatureSource,
)


TRIVY_VULNERABILITIES = {
    "trivy_vuln_critical": FeatureMetadata(
        display_name="Critical Vulnerabilities",
        description="Number of critical severity vulnerabilities found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="2",
    ),
    "trivy_vuln_high": FeatureMetadata(
        display_name="High Vulnerabilities",
        description="Number of high severity vulnerabilities found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="5",
    ),
    "trivy_vuln_medium": FeatureMetadata(
        display_name="Medium Vulnerabilities",
        description="Number of medium severity vulnerabilities found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="12",
    ),
    "trivy_vuln_low": FeatureMetadata(
        display_name="Low Vulnerabilities",
        description="Number of low severity vulnerabilities found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="8",
    ),
    "trivy_vuln_total": FeatureMetadata(
        display_name="Total Vulnerabilities",
        description="Total number of vulnerabilities found across all severity levels",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="27",
    ),
}


TRIVY_MISCONFIGURATIONS = {
    "trivy_misconfig_critical": FeatureMetadata(
        display_name="Critical Misconfigurations",
        description="Number of critical IaC misconfigurations (Terraform, Kubernetes, etc.)",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="1",
    ),
    "trivy_misconfig_high": FeatureMetadata(
        display_name="High Misconfigurations",
        description="Number of high severity IaC misconfigurations",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="3",
    ),
    "trivy_misconfig_medium": FeatureMetadata(
        display_name="Medium Misconfigurations",
        description="Number of medium severity IaC misconfigurations",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="7",
    ),
    "trivy_misconfig_low": FeatureMetadata(
        display_name="Low Misconfigurations",
        description="Number of low severity IaC misconfigurations",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="4",
    ),
    "trivy_misconfig_total": FeatureMetadata(
        display_name="Total Misconfigurations",
        description="Total number of IaC misconfigurations found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="15",
    ),
}


TRIVY_OTHER = {
    "trivy_secrets_count": FeatureMetadata(
        display_name="Secrets Found",
        description="Number of exposed secrets detected (API keys, passwords, tokens)",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="0",
    ),
    "trivy_scan_duration_ms": FeatureMetadata(
        display_name="Scan Duration",
        description="Time taken to complete Trivy scan",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="2340",
        unit="ms",
    ),
    "trivy_packages_scanned": FeatureMetadata(
        display_name="Packages Scanned",
        description="Number of packages analyzed for vulnerabilities",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="156",
    ),
    "trivy_files_scanned": FeatureMetadata(
        display_name="Files Scanned",
        description="Number of files analyzed for security issues",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="42",
    ),
    "trivy_has_critical": FeatureMetadata(
        display_name="Has Critical Vulnerabilities",
        description="Whether any critical vulnerabilities were found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.BOOLEAN,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="true",
    ),
    "trivy_has_high": FeatureMetadata(
        display_name="Has High Vulnerabilities",
        description="Whether any high severity vulnerabilities were found",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.BOOLEAN,
        source=FeatureSource.TRIVY,
        nullable=False,
        example_value="true",
    ),
    "trivy_top_vulnerable_packages": FeatureMetadata(
        display_name="Top Vulnerable Packages",
        description="List of top 10 vulnerable packages with severity and CVE details",
        category=FeatureCategory.SECURITY,
        data_type=FeatureDataType.JSON,
        source=FeatureSource.TRIVY,
        nullable=True,
        example_value='[{"name": "lodash", "severity": "high", "cve": "CVE-2021-23337"}]',
    ),
}


TRIVY_METADATA = {
    **TRIVY_VULNERABILITIES,
    **TRIVY_MISCONFIGURATIONS,
    **TRIVY_OTHER,
}
