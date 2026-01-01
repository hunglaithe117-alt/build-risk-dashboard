"""
Statistics Service - Calculate and aggregate statistics for dataset versions.

Provides comprehensive statistics including:
- Build status breakdowns
- Feature completeness metrics
- Value distributions (histograms for numeric, counts for categorical)
- Correlation matrices between numeric features
"""

import logging
import statistics
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo.database import Database

from app.dtos.statistics import (
    BuildStatusBreakdown,
    CategoricalDistribution,
    CategoricalValue,
    CorrelationMatrixResponse,
    CorrelationPair,
    FeatureCompleteness,
    FeatureDistributionResponse,
    HistogramBin,
    NumericDistribution,
    NumericStats,
    VersionStatistics,
    VersionStatisticsResponse,
)
from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.repositories.data_quality_repository import DataQualityRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.services.feature_service import FeatureService
from app.tasks.pipeline.feature_dag._feature_definitions import get_feature_data_type

logger = logging.getLogger(__name__)


class StatisticsService:
    """Service for calculating dataset version statistics."""

    def __init__(self, db: Database):
        self.db = db
        self.version_repo = DatasetVersionRepository(db)
        self.build_repo = DatasetEnrichmentBuildRepository(db)
        self.quality_repo = DataQualityRepository(db)
        self.feature_service = FeatureService()

    def get_version_statistics(self, dataset_id: str, version_id: str) -> VersionStatisticsResponse:
        """
        Get comprehensive statistics for a dataset version.

        Args:
            dataset_id: Dataset ID
            version_id: Version ID

        Returns:
            VersionStatisticsResponse with all statistics
        """
        # Get version
        version = self.version_repo.find_by_id(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        if str(version.dataset_id) != dataset_id:
            raise HTTPException(status_code=404, detail="Version not found in dataset")

        # Get all enrichment builds with features from FeatureVector
        builds = self.build_repo.find_by_version_with_features(version_id)

        # Calculate statistics
        stats = self._calculate_version_stats(version, builds)

        # Get build status breakdown
        status_breakdown = self._calculate_status_breakdown(builds)

        # Get feature completeness
        feature_completeness = self._calculate_feature_completeness(
            builds, version.selected_features
        )

        # Get quality scores if available
        quality_report = self.quality_repo.find_by_version(version_id)
        if quality_report and quality_report.status == "completed":
            stats.quality_score = quality_report.quality_score
            stats.completeness_score = quality_report.completeness_score
            stats.validity_score = quality_report.validity_score
            stats.consistency_score = quality_report.consistency_score
            stats.coverage_score = quality_report.coverage_score

        return VersionStatisticsResponse(
            version_id=version_id,
            dataset_id=dataset_id,
            version_name=version.name or f"v{version.version_number}",
            status=version.status if isinstance(version.status, str) else version.status.value,
            statistics=stats,
            build_status_breakdown=status_breakdown,
            feature_completeness=feature_completeness,
            started_at=version.started_at,
            completed_at=version.completed_at,
            evaluated_at=quality_report.completed_at if quality_report else None,
        )

    def get_feature_distributions(
        self,
        dataset_id: str,
        version_id: str,
        features: Optional[List[str]] = None,
        bins: int = 20,
        top_n: int = 20,
    ) -> FeatureDistributionResponse:
        """
        Get value distributions for selected features.

        Args:
            dataset_id: Dataset ID
            version_id: Version ID
            features: Optional list of features (defaults to all selected)
            bins: Number of histogram bins for numeric features
            top_n: Max categorical values to return

        Returns:
            FeatureDistributionResponse with distribution data
        """
        version = self.version_repo.find_by_id(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        # Get features to analyze
        target_features = features or version.selected_features
        if not target_features:
            return FeatureDistributionResponse(version_id=version_id, distributions={})

        # Get all builds with features from FeatureVector
        builds = self.build_repo.find_by_version_with_features(version_id)

        distributions: Dict[str, Any] = {}

        for feature_name in target_features:
            # Collect all values for this feature
            values = []
            for build in builds:
                features = build.get("features", {})
                if features and feature_name in features:
                    values.append(features[feature_name])

            if not values:
                continue

            # Get data type from registry, fallback to inference
            data_type = get_feature_data_type(feature_name)
            if data_type == "unknown":
                data_type = self._infer_data_type(values)

            if data_type in ("integer", "float"):
                dist = self._calculate_numeric_distribution(feature_name, values, bins=bins)
            else:
                dist = self._calculate_categorical_distribution(feature_name, values, top_n=top_n)

            distributions[feature_name] = dist.model_dump()

        return FeatureDistributionResponse(version_id=version_id, distributions=distributions)

    def get_correlation_matrix(
        self,
        dataset_id: str,
        version_id: str,
        features: Optional[List[str]] = None,
    ) -> CorrelationMatrixResponse:
        """
        Calculate correlation matrix between numeric features.

        Args:
            dataset_id: Dataset ID
            version_id: Version ID
            features: Optional list of features (defaults to all numeric)

        Returns:
            CorrelationMatrixResponse with matrix and significant pairs
        """
        version = self.version_repo.find_by_id(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")

        # Get feature metadata
        all_features = self.feature_service.list_features()
        numeric_features = [
            f["name"]
            for f in all_features
            if f["data_type"] in ("integer", "float", "numeric")
            and f["name"] in (features or version.selected_features)
        ]

        if not numeric_features:
            return CorrelationMatrixResponse(
                version_id=version_id, features=[], matrix=[], significant_pairs=[]
            )

        # Get all builds with features from FeatureVector
        builds = self.build_repo.find_by_version_with_features(version_id)

        # Build value matrix
        feature_values: Dict[str, List[Optional[float]]] = {f: [] for f in numeric_features}

        for build in builds:
            for feature in numeric_features:
                value = None
                features = build.get("features", {})
                if features and feature in features:
                    try:
                        value = float(features[feature])
                    except (ValueError, TypeError):
                        pass
                feature_values[feature].append(value)

        # Calculate correlation matrix
        matrix: List[List[Optional[float]]] = []
        significant_pairs: List[CorrelationPair] = []

        for i, f1 in enumerate(numeric_features):
            row: List[Optional[float]] = []
            for j, f2 in enumerate(numeric_features):
                if i == j:
                    row.append(1.0)
                elif i > j:
                    # Already calculated, copy symmetric value
                    row.append(matrix[j][i])
                else:
                    corr = self._calculate_correlation(feature_values[f1], feature_values[f2])
                    row.append(corr)

                    # Track significant correlations
                    if corr is not None and abs(corr) >= 0.5:
                        strength = self._get_correlation_strength(corr)
                        significant_pairs.append(
                            CorrelationPair(
                                feature_1=f1,
                                feature_2=f2,
                                correlation=corr,
                                strength=strength,
                            )
                        )
            matrix.append(row)

        # Sort significant pairs by absolute correlation
        significant_pairs.sort(key=lambda p: abs(p.correlation), reverse=True)

        return CorrelationMatrixResponse(
            version_id=version_id,
            features=numeric_features,
            matrix=matrix,
            significant_pairs=significant_pairs,
        )

    # =========================================================================
    # Private Helper Methods
    # =========================================================================

    def _infer_data_type(self, values: List[Any]) -> str:
        """
        Infer data type from actual values.

        Returns:
            'integer', 'float', 'boolean', 'categorical', or 'unknown'
        """
        non_null_values = [v for v in values if v is not None and v != ""]

        if not non_null_values:
            return "unknown"

        # Sample up to 100 values for type inference
        sample = non_null_values[:100]

        # Skip complex types (dicts, lists) - treat as categorical
        if any(isinstance(v, (list, dict)) for v in sample):
            return "categorical"

        # Check if all values are boolean
        bool_values = {True, False, "true", "false", "True", "False", 1, 0}
        try:
            if all(v in bool_values for v in sample):
                return "boolean"
        except TypeError:
            # Unhashable type - not boolean
            pass

        # Check if all values are numeric
        numeric_count = 0
        int_count = 0
        float_count = 0

        for v in sample:
            if isinstance(v, bool):
                continue
            elif isinstance(v, int):
                numeric_count += 1
                int_count += 1
            elif isinstance(v, float):
                numeric_count += 1
                if v == int(v):
                    int_count += 1
                else:
                    float_count += 1
            elif isinstance(v, str):
                try:
                    f = float(v)
                    numeric_count += 1
                    if f == int(f):
                        int_count += 1
                    else:
                        float_count += 1
                except (ValueError, TypeError):
                    pass

        # If >80% are numeric, classify as numeric
        if len(sample) > 0 and numeric_count / len(sample) >= 0.8:
            if float_count > 0:
                return "float"
            return "integer"

        # Otherwise categorical
        return "categorical"

    def _calculate_version_stats(
        self, version, builds: List[DatasetEnrichmentBuild]
    ) -> VersionStatistics:
        """Calculate aggregate version statistics."""
        total = len(builds)

        if total == 0:
            return VersionStatistics(total_features_selected=len(version.selected_features or []))

        enriched = sum(1 for b in builds if b.get("features") and len(b.get("features", {})) > 0)
        failed = sum(1 for b in builds if b.get("extraction_status") == "failed")
        partial = sum(
            1
            for b in builds
            if b.get("features")
            and 0 < len(b.get("features", {})) < len(version.selected_features or [])
        )

        # Calculate feature stats
        total_features = sum(len(b.get("features", {})) for b in builds if b.get("features"))
        avg_features = total_features / enriched if enriched > 0 else 0

        # Processing duration
        duration = None
        if version.started_at and version.completed_at:
            duration = (version.completed_at - version.started_at).total_seconds()

        return VersionStatistics(
            total_builds=total,
            enriched_builds=enriched,
            failed_builds=failed,
            partial_builds=partial,
            enrichment_rate=(enriched / total * 100) if total > 0 else 0,
            success_rate=(enriched / (enriched + failed) * 100 if (enriched + failed) > 0 else 0),
            total_features_selected=len(version.selected_features or []),
            avg_features_per_build=round(avg_features, 2),
            total_feature_values_extracted=total_features,
            processing_duration_seconds=duration,
        )

    def _calculate_status_breakdown(
        self, builds: List[DatasetEnrichmentBuild]
    ) -> List[BuildStatusBreakdown]:
        """Calculate build status breakdown."""
        total = len(builds)
        if total == 0:
            return []

        status_counts: Dict[str, int] = Counter()

        for build in builds:
            status = build.get("extraction_status", "pending")
            if isinstance(status, str):
                status_counts[status] += 1
            else:
                status_counts[status.value] += 1

        return [
            BuildStatusBreakdown(
                status=status,
                count=count,
                percentage=round(count / total * 100, 1),
            )
            for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True)
        ]

    def _calculate_feature_completeness(
        self, builds: List[DatasetEnrichmentBuild], selected_features: List[str]
    ) -> List[FeatureCompleteness]:
        """Calculate completeness for each feature."""
        if not builds or not selected_features:
            return []

        total = len(builds)
        completeness_list: List[FeatureCompleteness] = []

        for feature in selected_features:
            # Collect values for this feature
            values = [
                b.get("features", {})[feature]
                for b in builds
                if b.get("features") and feature in b.get("features", {})
            ]

            non_null = sum(1 for v in values if v is not None)
            null_count = total - non_null

            # Get data type from registry, fallback to inference
            data_type = get_feature_data_type(feature)
            if data_type == "unknown" and values:
                data_type = self._infer_data_type(values)

            completeness_list.append(
                FeatureCompleteness(
                    feature_name=feature,
                    non_null_count=non_null,
                    null_count=null_count,
                    completeness_pct=round(non_null / total * 100, 1) if total > 0 else 0,
                    data_type=data_type,
                )
            )

        # Sort by completeness ascending (worst first)
        completeness_list.sort(key=lambda x: x.completeness_pct)

        return completeness_list

    def _calculate_numeric_distribution(
        self, feature_name: str, values: List[Any], bins: int = 20
    ) -> NumericDistribution:
        """Calculate histogram distribution for numeric feature."""
        # Filter to valid numeric values
        numeric_values: List[float] = []
        null_count = 0

        for v in values:
            if v is None:
                null_count += 1
            else:
                try:
                    numeric_values.append(float(v))
                except (ValueError, TypeError):
                    null_count += 1

        if not numeric_values:
            return NumericDistribution(
                feature_name=feature_name,
                total_count=len(values),
                null_count=null_count,
                bins=[],
                stats=None,
            )

        # Calculate stats
        sorted_values = sorted(numeric_values)
        n = len(sorted_values)

        stats = NumericStats(
            min=min(numeric_values),
            max=max(numeric_values),
            mean=statistics.mean(numeric_values),
            median=statistics.median(numeric_values),
            std=statistics.stdev(numeric_values) if n > 1 else 0,
            q1=sorted_values[n // 4] if n >= 4 else sorted_values[0],
            q3=sorted_values[3 * n // 4] if n >= 4 else sorted_values[-1],
            iqr=0,  # Will calculate below
        )
        stats.iqr = stats.q3 - stats.q1

        # Create histogram bins
        min_val, max_val = stats.min, stats.max
        bin_width = (max_val - min_val) / bins if max_val > min_val else 1

        histogram_bins: List[HistogramBin] = []
        for i in range(bins):
            bin_min = min_val + i * bin_width
            bin_max = min_val + (i + 1) * bin_width

            # Count values in this bin
            if i == bins - 1:
                count = sum(1 for v in numeric_values if bin_min <= v <= bin_max)
            else:
                count = sum(1 for v in numeric_values if bin_min <= v < bin_max)

            histogram_bins.append(
                HistogramBin(
                    min_value=round(bin_min, 4),
                    max_value=round(bin_max, 4),
                    count=count,
                    percentage=round(count / n * 100, 1) if n > 0 else 0,
                )
            )

        return NumericDistribution(
            feature_name=feature_name,
            total_count=len(values),
            null_count=null_count,
            bins=histogram_bins,
            stats=stats,
        )

    def _calculate_categorical_distribution(
        self, feature_name: str, values: List[Any], top_n: int = 20
    ) -> CategoricalDistribution:
        """Calculate value counts for categorical feature."""
        null_count = 0
        string_values: List[str] = []

        for v in values:
            if v is None or v == "":
                null_count += 1
            else:
                string_values.append(str(v))

        if not string_values:
            return CategoricalDistribution(
                feature_name=feature_name,
                total_count=len(values),
                null_count=null_count,
                unique_count=0,
                values=[],
            )

        # Count values
        value_counts = Counter(string_values)
        unique_count = len(value_counts)
        total_non_null = len(string_values)

        # Get top N values
        top_values = value_counts.most_common(top_n)
        categorical_values = [
            CategoricalValue(
                value=value,
                count=count,
                percentage=round(count / total_non_null * 100, 1),
            )
            for value, count in top_values
        ]

        return CategoricalDistribution(
            feature_name=feature_name,
            total_count=len(values),
            null_count=null_count,
            unique_count=unique_count,
            values=categorical_values,
            truncated=unique_count > top_n,
        )

    def _calculate_correlation(
        self, x: List[Optional[float]], y: List[Optional[float]]
    ) -> Optional[float]:
        """Calculate Pearson correlation between two value lists."""
        # Filter to pairs where both values are not None
        pairs = [
            (xi, yi) for xi, yi in zip(x, y, strict=False) if xi is not None and yi is not None
        ]

        if len(pairs) < 3:
            return None

        x_vals = [p[0] for p in pairs]
        y_vals = [p[1] for p in pairs]

        n = len(pairs)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xy = sum(xi * yi for xi, yi in pairs)
        sum_x2 = sum(xi**2 for xi in x_vals)
        sum_y2 = sum(yi**2 for yi in y_vals)

        # Pearson correlation formula
        numerator = n * sum_xy - sum_x * sum_y
        denominator_x = n * sum_x2 - sum_x**2
        denominator_y = n * sum_y2 - sum_y**2

        if denominator_x <= 0 or denominator_y <= 0:
            return None

        denominator = (denominator_x * denominator_y) ** 0.5

        if denominator == 0:
            return None

        correlation = numerator / denominator

        # Clamp to [-1, 1] due to floating point errors
        return round(max(-1, min(1, correlation)), 4)

    def _get_correlation_strength(self, corr: float) -> str:
        """Get human-readable correlation strength."""
        abs_corr = abs(corr)
        if abs_corr >= 0.8:
            return "strong_positive" if corr > 0 else "strong_negative"
        elif abs_corr >= 0.5:
            return "moderate_positive" if corr > 0 else "moderate_negative"
        else:
            return "weak"
