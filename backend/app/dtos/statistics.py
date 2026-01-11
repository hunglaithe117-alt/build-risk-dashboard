"""
Statistics DTOs - Data transfer objects for statistics endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Version Statistics DTOs
# =============================================================================


class VersionStatistics(BaseModel):
    """Aggregate statistics for a dataset version."""

    # Build counts
    total_builds: int = 0
    enriched_builds: int = 0
    failed_builds: int = 0
    partial_builds: int = 0

    # Rates
    enrichment_rate: float = 0.0  # enriched / total * 100
    success_rate: float = 0.0  # enriched / (enriched + failed) * 100

    # Feature stats
    total_features_selected: int = 0
    avg_features_per_build: float = 0.0
    total_feature_values_extracted: int = 0

    # Quality (if evaluated)
    quality_score: Optional[float] = None
    completeness_score: Optional[float] = None
    validity_score: Optional[float] = None
    consistency_score: Optional[float] = None
    coverage_score: Optional[float] = None

    # Processing time
    processing_duration_seconds: Optional[float] = None


class BuildStatusBreakdown(BaseModel):
    """Breakdown of build statuses."""

    status: str  # "completed", "failed", "partial", "pending"
    count: int
    percentage: float


class FeatureCompleteness(BaseModel):
    """Completeness metric for a single feature."""

    feature_name: str
    non_null_count: int
    null_count: int
    completeness_pct: float
    data_type: str


class VersionStatisticsResponse(BaseModel):
    """Complete statistics response for a scenario."""

    scenario_id: str
    scenario_name: str
    status: str

    # Summary statistics
    statistics: VersionStatistics

    # Breakdowns
    build_status_breakdown: List[BuildStatusBreakdown] = Field(default_factory=list)
    feature_completeness: List[FeatureCompleteness] = Field(default_factory=list)

    # Timestamps
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    evaluated_at: Optional[datetime] = None


# Feature Distribution DTOs
class HistogramBin(BaseModel):
    """Single bin in a histogram."""

    min_value: float
    max_value: float
    count: int
    percentage: float


class NumericStats(BaseModel):
    """Statistics for a numeric feature."""

    min: float
    max: float
    mean: float
    median: float
    std: float
    q1: float  # 25th percentile
    q3: float  # 75th percentile
    iqr: float  # Interquartile range


class NumericDistribution(BaseModel):
    """Distribution data for a numeric feature."""

    feature_name: str
    data_type: str = "numeric"
    total_count: int
    null_count: int
    bins: List[HistogramBin] = Field(default_factory=list)
    stats: Optional[NumericStats] = None


class CategoricalValue(BaseModel):
    """Single value count for categorical feature."""

    value: str
    count: int
    percentage: float


class CategoricalDistribution(BaseModel):
    """Distribution data for a categorical feature."""

    feature_name: str
    data_type: str = "categorical"
    total_count: int
    null_count: int
    unique_count: int
    values: List[CategoricalValue] = Field(default_factory=list)
    truncated: bool = False  # True if more values exist than shown


class FeatureDistributionResponse(BaseModel):
    """Response for feature distribution endpoint."""

    scenario_id: str
    distributions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Map of feature_name -> NumericDistribution or CategoricalDistribution",
    )


# Correlation Matrix DTOs
class CorrelationPair(BaseModel):
    """A significant correlation pair."""

    feature_1: str
    feature_2: str
    correlation: float
    strength: str  # "strong_positive", "strong_negative", "moderate", "weak"


class CorrelationMatrixResponse(BaseModel):
    """Response for correlation matrix endpoint."""

    scenario_id: str
    features: List[str]  # Feature names in order
    matrix: List[
        List[Optional[float]]
    ]  # 2D correlation matrix (None for non-numeric pairs)
    significant_pairs: List[CorrelationPair] = Field(
        default_factory=list,
        description="Pairs with |correlation| > 0.7",
    )
