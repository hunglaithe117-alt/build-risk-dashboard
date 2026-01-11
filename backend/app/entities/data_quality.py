"""
Data Quality Report Entity - Stores quality evaluation results for dataset versions.

This module provides entities for tracking data quality assessments,
including per-feature metrics and overall quality scores.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .base import BaseEntity, PyObjectId


class QualityEvaluationStatus(str, Enum):
    """Quality evaluation status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QualityIssueSeverity(str, Enum):
    """Severity level for quality issues."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityIssue(BaseModel):
    """A quality issue detected during evaluation."""

    severity: QualityIssueSeverity = QualityIssueSeverity.WARNING
    category: str  # "completeness", "validity", "consistency", "coverage"
    feature_name: Optional[str] = None  # None for version-level issues
    message: str
    details: Optional[Dict[str, Any]] = None


class DataQualityMetric(BaseModel):
    """Quality metrics for a single feature."""

    feature_name: str
    data_type: str  # "integer", "float", "boolean", "string", "list"

    # Completeness metrics
    total_values: int = 0
    null_count: int = 0
    completeness_pct: float = 100.0  # (total - null) / total * 100

    # For numeric features
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    std_dev: Optional[float] = None

    # For string features
    unique_count: Optional[int] = None
    empty_string_count: int = 0

    # Validity check (based on valid_range from metadata)
    expected_range: Optional[Tuple[float, float]] = None
    expected_values: Optional[List[str]] = None
    out_of_range_count: int = 0
    invalid_value_count: int = 0
    validity_pct: float = 100.0

    # Issues specific to this feature
    issues: List[str] = Field(default_factory=list)


class DataQualityReport(BaseEntity):
    """
    Quality evaluation report for a dataset version.

    Stores comprehensive quality assessment including:
    - Overall quality scores
    - Per-feature metrics
    - Detected issues
    - Evaluation metadata
    """

    class Config:
        collection = "data_quality_reports"
        use_enum_values = True

    # References
    scenario_id: PyObjectId = Field(..., description="Reference to training_scenarios")

    # Overall scores (0-100)
    # Formula: 0.4*completeness + 0.3*validity + 0.2*consistency + 0.1*coverage
    quality_score: float = 0.0
    completeness_score: float = 0.0  # % features non-null
    validity_score: float = 0.0  # % values within valid range
    consistency_score: float = 0.0  # % builds with all selected features
    coverage_score: float = 0.0  # % successfully enriched builds

    # Detailed metrics per feature
    feature_metrics: List[DataQualityMetric] = Field(default_factory=list)

    # Summary statistics
    total_builds: int = 0
    enriched_builds: int = 0
    partial_builds: int = 0  # Builds with some features extracted
    failed_builds: int = 0
    total_features: int = 0
    features_with_issues: int = 0

    # Issues found
    issues: List[QualityIssue] = Field(default_factory=list)

    # Status
    status: QualityEvaluationStatus = QualityEvaluationStatus.PENDING
    error_message: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def get_issue_count_by_severity(self) -> Dict[str, int]:
        """Get count of issues by severity level."""
        counts = {"info": 0, "warning": 0, "error": 0}
        for issue in self.issues:
            severity = (
                issue.severity
                if isinstance(issue.severity, str)
                else issue.severity.value
            )
            if severity in counts:
                counts[severity] += 1
        return counts

    def mark_started(self) -> "DataQualityReport":
        """Mark evaluation as started."""
        self.status = QualityEvaluationStatus.RUNNING
        self.started_at = datetime.utcnow()
        return self

    def mark_completed(self, quality_score: float) -> "DataQualityReport":
        """Mark evaluation as completed."""
        self.status = QualityEvaluationStatus.COMPLETED
        self.quality_score = quality_score
        self.completed_at = datetime.utcnow()
        return self

    def mark_failed(self, error: str) -> "DataQualityReport":
        """Mark evaluation as failed."""
        self.status = QualityEvaluationStatus.FAILED
        self.error_message = error
        self.completed_at = datetime.utcnow()
        return self
