"""DTOs for Data Quality API."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel


class QualityIssueResponse(BaseModel):
    """A quality issue detected during evaluation."""

    severity: str  # "info", "warning", "error"
    category: str  # "completeness", "validity", "consistency", "coverage"
    feature_name: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None


class QualityMetricResponse(BaseModel):
    """Quality metrics for a single feature."""

    feature_name: str
    data_type: str
    total_values: int
    null_count: int
    completeness_pct: float
    validity_pct: float

    # Numeric stats
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    std_dev: Optional[float] = None

    # Validity
    expected_range: Optional[Tuple[float, float]] = None
    out_of_range_count: int = 0
    invalid_value_count: int = 0

    # Issues
    issues: List[str] = []


class QualityReportSummaryResponse(BaseModel):
    """Summary of a quality report (for listings)."""

    id: str
    scenario_id: str
    status: str
    quality_score: float
    completeness_score: float
    validity_score: float
    consistency_score: float
    coverage_score: float
    total_builds: int
    enriched_builds: int
    total_features: int
    issue_count: int
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class QualityReportResponse(BaseModel):
    """Full quality report with details."""

    id: str
    scenario_id: str
    status: str
    error_message: Optional[str] = None

    # Scores
    quality_score: float
    completeness_score: float
    validity_score: float
    consistency_score: float
    coverage_score: float

    # Stats
    total_builds: int
    enriched_builds: int
    partial_builds: int
    failed_builds: int
    total_features: int
    features_with_issues: int

    # Details
    feature_metrics: List[QualityMetricResponse] = []
    issues: List[QualityIssueResponse] = []

    # Issue counts by severity
    issue_counts: Dict[str, int] = {}

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class EvaluateQualityRequest(BaseModel):
    """Request body for triggering quality evaluation."""

    pass  # No additional fields needed, uses path params


class EvaluateQualityResponse(BaseModel):
    """Response after triggering quality evaluation."""

    report_id: str
    status: str
    message: str
