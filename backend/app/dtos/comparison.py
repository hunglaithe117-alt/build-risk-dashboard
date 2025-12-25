"""DTOs for dataset comparison."""

from typing import List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Request DTOs
# =============================================================================


class CompareInternalRequest(BaseModel):
    """Request to compare two internal dataset versions."""

    base_dataset_id: str = Field(..., description="Base dataset ID")
    base_version_id: str = Field(..., description="Base version ID")
    target_dataset_id: str = Field(..., description="Target dataset ID")
    target_version_id: str = Field(..., description="Target version ID")


# =============================================================================
# Response DTOs
# =============================================================================


class VersionSummary(BaseModel):
    """Summary of a version for comparison."""

    dataset_id: str
    dataset_name: str
    version_id: str
    version_name: str
    total_rows: int
    total_features: int
    selected_features: List[str]
    enriched_rows: int
    completeness_pct: float = Field(description="Overall completeness percentage")


class ExternalDatasetSummary(BaseModel):
    """Summary of an uploaded external dataset."""

    filename: str
    total_rows: int
    total_columns: int
    columns: List[str]


class FeatureComparisonItem(BaseModel):
    """Single feature comparison."""

    feature_name: str
    in_base: bool
    in_target: bool
    base_null_pct: Optional[float] = None
    target_null_pct: Optional[float] = None
    base_coverage_pct: Optional[float] = None
    target_coverage_pct: Optional[float] = None


class FeatureComparison(BaseModel):
    """Feature-level comparison results."""

    common_features: List[str] = Field(description="Features in both versions")
    base_only_features: List[str] = Field(description="Features only in base")
    target_only_features: List[str] = Field(description="Features only in target")
    feature_details: List[FeatureComparisonItem] = Field(
        default_factory=list, description="Detailed comparison per feature"
    )


class QualityComparison(BaseModel):
    """Data quality comparison."""

    base_completeness_pct: float
    target_completeness_pct: float
    base_avg_null_pct: float
    target_avg_null_pct: float
    completeness_diff: float = Field(description="Target - Base completeness")


class RowOverlap(BaseModel):
    """Row overlap analysis (by commit_sha if available)."""

    base_total_rows: int
    target_total_rows: int
    overlapping_rows: int = Field(description="Rows with matching commit_sha")
    overlap_pct: float = Field(description="Overlap percentage")
    base_only_rows: int
    target_only_rows: int


class CompareResponse(BaseModel):
    """Full comparison response."""

    comparison_type: str = Field(description="'internal' or 'external'")
    base: VersionSummary
    target: Optional[VersionSummary] = None
    external_target: Optional[ExternalDatasetSummary] = None
    feature_comparison: FeatureComparison
    quality_comparison: QualityComparison
    row_overlap: Optional[RowOverlap] = None


class CompareExternalResponse(BaseModel):
    """Response for external dataset comparison."""

    comparison_type: str = "external"
    base: VersionSummary
    external_target: ExternalDatasetSummary
    feature_comparison: FeatureComparison
    quality_comparison: QualityComparison
