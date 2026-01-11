"""
Scan Statistics DTOs - Data transfer objects for scan metrics statistics endpoints.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class MetricSummary(BaseModel):
    """Aggregate summary for a single metric."""

    sum: float = 0
    avg: float = 0
    max: float = 0
    min: float = 0
    count: int = 0  # Non-null count


class TrivySummary(BaseModel):
    """Trivy scan metrics summary."""

    # Vulnerability metrics
    vuln_total: MetricSummary = Field(default_factory=MetricSummary)
    vuln_critical: MetricSummary = Field(default_factory=MetricSummary)
    vuln_high: MetricSummary = Field(default_factory=MetricSummary)
    vuln_medium: MetricSummary = Field(default_factory=MetricSummary)
    vuln_low: MetricSummary = Field(default_factory=MetricSummary)

    # Misconfiguration metrics
    misconfig_total: MetricSummary = Field(default_factory=MetricSummary)
    misconfig_critical: MetricSummary = Field(default_factory=MetricSummary)
    misconfig_high: MetricSummary = Field(default_factory=MetricSummary)
    misconfig_medium: MetricSummary = Field(default_factory=MetricSummary)
    misconfig_low: MetricSummary = Field(default_factory=MetricSummary)

    # Other metrics
    secrets_count: MetricSummary = Field(default_factory=MetricSummary)
    scan_duration_ms: MetricSummary = Field(default_factory=MetricSummary)

    # Counts
    has_critical_count: int = 0  # Builds with critical vulns
    has_high_count: int = 0  # Builds with high vulns
    total_scans: int = 0


class SonarSummary(BaseModel):
    """SonarQube scan metrics summary."""

    # Core metrics
    bugs: MetricSummary = Field(default_factory=MetricSummary)
    code_smells: MetricSummary = Field(default_factory=MetricSummary)
    vulnerabilities: MetricSummary = Field(default_factory=MetricSummary)
    security_hotspots: MetricSummary = Field(default_factory=MetricSummary)

    # Quality metrics
    complexity: MetricSummary = Field(default_factory=MetricSummary)
    cognitive_complexity: MetricSummary = Field(default_factory=MetricSummary)
    duplicated_lines_density: MetricSummary = Field(default_factory=MetricSummary)
    ncloc: MetricSummary = Field(default_factory=MetricSummary)

    # Rating counts (1=A, 2=B, 3=C, 4=D, 5=E)
    reliability_rating_avg: Optional[float] = None
    security_rating_avg: Optional[float] = None
    maintainability_rating_avg: Optional[float] = None

    # Status counts
    alert_status_ok_count: int = 0
    alert_status_error_count: int = 0
    total_scans: int = 0


class ScanSummary(BaseModel):
    """Overall scan summary."""

    total_builds: int = 0
    builds_with_trivy: int = 0
    builds_with_sonar: int = 0
    builds_with_any_scan: int = 0
    trivy_coverage_pct: float = 0
    sonar_coverage_pct: float = 0


class ScanMetricsStatisticsResponse(BaseModel):
    """Complete scan metrics statistics response."""

    scenario_id: str
    scan_summary: ScanSummary = Field(default_factory=ScanSummary)
    trivy_summary: TrivySummary = Field(default_factory=TrivySummary)
    sonar_summary: SonarSummary = Field(default_factory=SonarSummary)


class ScanMetricDistribution(BaseModel):
    """Distribution data for a scan metric (for charts)."""

    metric_name: str
    values: List[float] = Field(default_factory=list)
    labels: List[str] = Field(default_factory=list)  # e.g., severity levels
