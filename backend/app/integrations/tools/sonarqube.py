"""
SonarQube Integration Tool

Provides code quality analysis via SonarQube.
Uses async scan mode - results are delivered via webhook after scan completes.
"""

from typing import Any, Dict, List, Optional
import logging

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
# SONARQUBE METRICS DEFINITIONS
# =============================================================================
# Preserved from pipeline/feature_metadata/sonar.py

SONARQUBE_METRICS: List[MetricDefinition] = [
    # -------------------------------------------------------------------------
    # Reliability Metrics (Bugs)
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="bugs",
        display_name="Bugs",
        description="Number of bug issues detected by SonarQube",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="5",
    ),
    MetricDefinition(
        key="reliability_issues",
        display_name="Reliability Issues",
        description="Total number of reliability issues",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="8",
    ),
    MetricDefinition(
        key="reliability_rating",
        display_name="Reliability Rating",
        description="Reliability rating (A-E) based on bug severity",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.STRING,
        example_value="A",
    ),
    MetricDefinition(
        key="reliability_remediation_effort",
        display_name="Reliability Remediation Effort",
        description="Estimated time to fix all reliability issues",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="120",
        unit="minutes",
    ),
    MetricDefinition(
        key="software_quality_reliability_rating",
        display_name="SW Quality Reliability Rating",
        description="Software quality reliability rating",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.STRING,
        example_value="B",
    ),
    MetricDefinition(
        key="software_quality_reliability_issues",
        display_name="SW Quality Reliability Issues",
        description="Software quality reliability issues count",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="3",
    ),
    MetricDefinition(
        key="software_quality_reliability_remediation_effort",
        display_name="SW Quality Reliability Remediation",
        description="Software quality reliability remediation effort",
        category=MetricCategory.RELIABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="60",
        unit="minutes",
    ),
    # -------------------------------------------------------------------------
    # Security Metrics (Vulnerabilities)
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="vulnerabilities",
        display_name="Vulnerabilities",
        description="Number of security vulnerabilities detected",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="2",
    ),
    MetricDefinition(
        key="security_issues",
        display_name="Security Issues",
        description="Total number of security issues",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="4",
    ),
    MetricDefinition(
        key="security_rating",
        display_name="Security Rating",
        description="Security rating (A-E) based on vulnerability severity",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.STRING,
        example_value="A",
    ),
    MetricDefinition(
        key="security_hotspots",
        display_name="Security Hotspots",
        description="Number of security hotspots that need review",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="3",
    ),
    MetricDefinition(
        key="security_remediation_effort",
        display_name="Security Remediation Effort",
        description="Estimated time to fix all security issues",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="180",
        unit="minutes",
    ),
    MetricDefinition(
        key="security_review_rating",
        display_name="Security Review Rating",
        description="Rating based on reviewed security hotspots",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.STRING,
        example_value="B",
    ),
    MetricDefinition(
        key="security_hotspots_to_review_status",
        display_name="Hotspots Review Status",
        description="Percentage of security hotspots that have been reviewed",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.FLOAT,
        example_value="75.0",
        unit="percent",
    ),
    MetricDefinition(
        key="software_quality_security_rating",
        display_name="SW Quality Security Rating",
        description="Software quality security rating",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.STRING,
        example_value="A",
    ),
    MetricDefinition(
        key="software_quality_security_issues",
        display_name="SW Quality Security Issues",
        description="Software quality security issues count",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="1",
    ),
    MetricDefinition(
        key="software_quality_security_remediation_effort",
        display_name="SW Quality Security Remediation",
        description="Software quality security remediation effort",
        category=MetricCategory.SECURITY,
        data_type=MetricDataType.INTEGER,
        example_value="30",
        unit="minutes",
    ),
    # -------------------------------------------------------------------------
    # Maintainability Metrics (Code Smells, Technical Debt)
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="code_smells",
        display_name="Code Smells",
        description="Number of code smell issues detected",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="42",
    ),
    MetricDefinition(
        key="sqale_index",
        display_name="Technical Debt",
        description="Total technical debt in minutes (SQALE index)",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="1200",
        unit="minutes",
    ),
    MetricDefinition(
        key="sqale_debt_ratio",
        display_name="Technical Debt Ratio",
        description="Ratio of technical debt to development cost",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.FLOAT,
        example_value="2.5",
        unit="percent",
    ),
    MetricDefinition(
        key="sqale_rating",
        display_name="Maintainability Rating",
        description="Maintainability rating (A-E) based on technical debt ratio",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.STRING,
        example_value="A",
    ),
    MetricDefinition(
        key="maintainability_issues",
        display_name="Maintainability Issues",
        description="Total number of maintainability issues",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="25",
    ),
    MetricDefinition(
        key="development_cost",
        display_name="Development Cost",
        description="Estimated development cost of the project",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.STRING,
        example_value="50000",
    ),
    MetricDefinition(
        key="effort_to_reach_maintainability_rating_a",
        display_name="Effort to Reach A Rating",
        description="Effort needed to reach maintainability rating A",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="480",
        unit="minutes",
    ),
    MetricDefinition(
        key="software_quality_maintainability_debt_ratio",
        display_name="SW Quality Debt Ratio",
        description="Software quality maintainability debt ratio",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.FLOAT,
        example_value="1.8",
        unit="percent",
    ),
    MetricDefinition(
        key="software_quality_maintainability_remediation_effort",
        display_name="SW Quality Maintainability Remediation",
        description="Software quality maintainability remediation effort",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="960",
        unit="minutes",
    ),
    MetricDefinition(
        key="software_quality_maintainability_rating",
        display_name="SW Quality Maintainability Rating",
        description="Software quality maintainability rating",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.STRING,
        example_value="B",
    ),
    MetricDefinition(
        key="effort_to_reach_software_quality_maintainability_rating_a",
        display_name="Effort to Reach SW Quality A Rating",
        description="Effort to reach software quality maintainability rating A",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="720",
        unit="minutes",
    ),
    MetricDefinition(
        key="software_quality_maintainability_issues",
        display_name="SW Quality Maintainability Issues",
        description="Software quality maintainability issues count",
        category=MetricCategory.MAINTAINABILITY,
        data_type=MetricDataType.INTEGER,
        example_value="18",
    ),
    # -------------------------------------------------------------------------
    # Coverage Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="coverage",
        display_name="Code Coverage",
        description="Overall code coverage percentage",
        category=MetricCategory.COVERAGE,
        data_type=MetricDataType.FLOAT,
        example_value="78.5",
        unit="percent",
    ),
    MetricDefinition(
        key="line_coverage",
        display_name="Line Coverage",
        description="Percentage of lines covered by tests",
        category=MetricCategory.COVERAGE,
        data_type=MetricDataType.FLOAT,
        example_value="82.3",
        unit="percent",
    ),
    MetricDefinition(
        key="lines_to_cover",
        display_name="Lines to Cover",
        description="Number of lines that should be covered by tests",
        category=MetricCategory.COVERAGE,
        data_type=MetricDataType.INTEGER,
        example_value="5000",
    ),
    MetricDefinition(
        key="uncovered_lines",
        display_name="Uncovered Lines",
        description="Number of lines not covered by tests",
        category=MetricCategory.COVERAGE,
        data_type=MetricDataType.INTEGER,
        example_value="885",
    ),
    # -------------------------------------------------------------------------
    # Duplication Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="duplicated_lines_density",
        display_name="Duplicated Lines %",
        description="Percentage of duplicated lines in the codebase",
        category=MetricCategory.DUPLICATION,
        data_type=MetricDataType.FLOAT,
        example_value="3.2",
        unit="percent",
    ),
    MetricDefinition(
        key="duplicated_lines",
        display_name="Duplicated Lines",
        description="Total number of duplicated lines",
        category=MetricCategory.DUPLICATION,
        data_type=MetricDataType.INTEGER,
        example_value="450",
    ),
    MetricDefinition(
        key="duplicated_blocks",
        display_name="Duplicated Blocks",
        description="Number of duplicated code blocks",
        category=MetricCategory.DUPLICATION,
        data_type=MetricDataType.INTEGER,
        example_value="12",
    ),
    MetricDefinition(
        key="duplicated_files",
        display_name="Duplicated Files",
        description="Number of files containing duplicated code",
        category=MetricCategory.DUPLICATION,
        data_type=MetricDataType.INTEGER,
        example_value="8",
    ),
    # -------------------------------------------------------------------------
    # Complexity Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="cognitive_complexity",
        display_name="Cognitive Complexity",
        description="Total cognitive complexity of the codebase",
        category=MetricCategory.COMPLEXITY,
        data_type=MetricDataType.INTEGER,
        example_value="1250",
    ),
    MetricDefinition(
        key="complexity",
        display_name="Cyclomatic Complexity",
        description="Total cyclomatic complexity of the codebase",
        category=MetricCategory.COMPLEXITY,
        data_type=MetricDataType.INTEGER,
        example_value="890",
    ),
    # -------------------------------------------------------------------------
    # Size Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="ncloc",
        display_name="Lines of Code (No Comments)",
        description="Number of physical lines containing code (excluding comments)",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="25000",
    ),
    MetricDefinition(
        key="lines",
        display_name="Total Lines",
        description="Total number of lines in the project",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="35000",
    ),
    MetricDefinition(
        key="files",
        display_name="Files Count",
        description="Total number of files analyzed",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="150",
    ),
    MetricDefinition(
        key="classes",
        display_name="Classes Count",
        description="Total number of classes",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="85",
    ),
    MetricDefinition(
        key="functions",
        display_name="Functions Count",
        description="Total number of functions",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="420",
    ),
    MetricDefinition(
        key="statements",
        display_name="Statements Count",
        description="Total number of statements",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="12500",
    ),
    MetricDefinition(
        key="ncloc_language_distribution",
        display_name="Language Distribution",
        description="Distribution of lines of code by language",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.STRING,
        example_value="py=15000;js=10000",
    ),
    MetricDefinition(
        key="comment_lines_density",
        display_name="Comment Density",
        description="Percentage of comment lines",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.FLOAT,
        example_value="18.5",
        unit="percent",
    ),
    MetricDefinition(
        key="comment_lines",
        display_name="Comment Lines",
        description="Total number of comment lines",
        category=MetricCategory.SIZE,
        data_type=MetricDataType.INTEGER,
        example_value="5500",
    ),
    # -------------------------------------------------------------------------
    # Quality Gate Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="alert_status",
        display_name="Quality Gate Status",
        description="Overall quality gate status (OK, WARN, ERROR)",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.STRING,
        example_value="OK",
    ),
    MetricDefinition(
        key="quality_gate_details",
        display_name="Quality Gate Details",
        description="Detailed quality gate conditions and their status",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.STRING,
        example_value='{"level":"OK","conditions":[...]}',
    ),
    # -------------------------------------------------------------------------
    # Issue Severity Metrics
    # -------------------------------------------------------------------------
    MetricDefinition(
        key="software_quality_blocker_issues",
        display_name="Blocker Issues",
        description="Number of blocker severity issues",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="0",
    ),
    MetricDefinition(
        key="critical_violations",
        display_name="Critical Violations",
        description="Number of critical severity violations",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="2",
    ),
    MetricDefinition(
        key="violations",
        display_name="Total Violations",
        description="Total number of all violations",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="47",
    ),
    MetricDefinition(
        key="software_quality_high_issues",
        display_name="High Severity Issues",
        description="Number of high severity issues",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="5",
    ),
    MetricDefinition(
        key="info_violations",
        display_name="Info Violations",
        description="Number of info severity violations",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="10",
    ),
    MetricDefinition(
        key="software_quality_low_issues",
        display_name="Low Severity Issues",
        description="Number of low severity issues",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="15",
    ),
    MetricDefinition(
        key="software_quality_info_issues",
        display_name="Info Level Issues",
        description="Number of info level quality issues",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="8",
    ),
    MetricDefinition(
        key="minor_violations",
        display_name="Minor Violations",
        description="Number of minor severity violations",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="20",
    ),
    MetricDefinition(
        key="major_violations",
        display_name="Major Violations",
        description="Number of major severity violations",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="12",
    ),
    MetricDefinition(
        key="software_quality_medium_issues",
        display_name="Medium Severity Issues",
        description="Number of medium severity issues",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="10",
    ),
    MetricDefinition(
        key="open_issues",
        display_name="Open Issues",
        description="Number of currently open issues",
        category=MetricCategory.CODE_QUALITY,
        data_type=MetricDataType.INTEGER,
        example_value="35",
    ),
    MetricDefinition(
        key="last_commit_date",
        display_name="Last Commit Date",
        description="Date of the last commit analyzed by SonarQube",
        category=MetricCategory.METADATA,
        data_type=MetricDataType.DATETIME,
        example_value="2024-01-15T10:30:00Z",
    ),
]


class SonarQubeTool(IntegrationTool):
    """
    SonarQube integration for code quality analysis.

    Uses async mode - scans are initiated and results are delivered via webhook.
    """

    def __init__(self):
        self._metrics = SONARQUBE_METRICS

    @property
    def tool_type(self) -> ToolType:
        return ToolType.SONARQUBE

    @property
    def display_name(self) -> str:
        return "SonarQube"

    @property
    def description(self) -> str:
        return "Code quality and security analysis"

    @property
    def scan_mode(self) -> ScanMode:
        return ScanMode.ASYNC  # Results via webhook

    def is_available(self) -> bool:
        """Check if SonarQube is configured."""
        return bool(
            getattr(settings, "SONAR_HOST_URL", None)
            and getattr(settings, "SONAR_TOKEN", None)
        )

    def get_config(self) -> Dict[str, Any]:
        """Return SonarQube configuration (without secrets)."""
        host_url = getattr(settings, "SONAR_HOST_URL", "")
        return {
            "host_url": host_url,
            "configured": self.is_available(),
            "webhook_required": True,
        }

    def get_scan_types(self) -> List[str]:
        """Return supported scan types."""
        return [
            "code_quality",
            "security",
            "maintainability",
            "reliability",
            "coverage",
        ]

    def get_metrics(self) -> List[MetricDefinition]:
        """Return all metric definitions."""
        return self._metrics

    def get_metric_keys(self) -> List[str]:
        """Return list of metric keys."""
        return [m.key for m in self._metrics]

    def get_metrics_by_category(
        self, category: MetricCategory
    ) -> List[MetricDefinition]:
        """Get metrics filtered by category."""
        return [m for m in self._metrics if m.category == category]

    def start_scan(
        self,
        repo_url: str,
        commit_sha: str,
        project_key: str,
        worktree_path: Optional[str] = None,
        config_content: Optional[str] = None,
    ) -> str:
        """
        Start an async SonarQube scan.

        Returns component_key for tracking the scan.
        Results will be delivered via webhook.
        """
        from app.services.sonar.runner import SonarCommitRunner

        runner = SonarCommitRunner(project_key)
        component_key = runner.scan_commit(
            repo_url=repo_url,
            commit_sha=commit_sha,
            sonar_config_content=config_content,
            shared_worktree_path=worktree_path,
        )
        return component_key

    def fetch_metrics(self, component_key: str) -> Dict[str, Any]:
        """
        Fetch metrics from SonarQube API for a given component.

        Usually called after webhook notification indicates scan is complete.
        """
        from app.services.sonar.exporter import MetricsExporter

        exporter = MetricsExporter()
        return exporter.collect_metrics(component_key)
