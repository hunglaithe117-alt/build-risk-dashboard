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

from app.dtos.scan_statistics import (
    MetricSummary,
    ScanMetricsStatisticsResponse,
    ScanSummary,
    SonarSummary,
    TrivySummary,
)
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
from app.entities.training_enrichment_build import TrainingEnrichmentBuild
from app.repositories.data_quality_repository import DataQualityRepository
from app.repositories.training_enrichment_build import TrainingEnrichmentBuildRepository
from app.repositories.training_scenario import TrainingScenarioRepository
from app.services.feature_service import FeatureService
from app.tasks.pipeline.feature_dag._feature_definitions import get_feature_data_type

logger = logging.getLogger(__name__)


class StatisticsService:
    """Service for calculating scenario statistics (replaces dataset version stats)."""

    def __init__(self, db: Database):
        self.db = db
        self.scenario_repo = TrainingScenarioRepository(db)
        self.build_repo = TrainingEnrichmentBuildRepository(db)
        self.quality_repo = DataQualityRepository(db)
        self.feature_service = FeatureService()

    def get_version_statistics(
        self, dataset_id: str, version_id: str
    ) -> VersionStatisticsResponse:
        """
        Get comprehensive statistics for a scenario.

        Args:
            dataset_id: Ignored (legacy param) or User ID owner
            version_id: Scenario ID

        Returns:
            VersionStatisticsResponse with all statistics
        """
        # Get scenario (formerly version)
        scenario = self.scenario_repo.find_by_id(version_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get all enrichment builds with features from FeatureVector (as dicts)
        builds = self.build_repo.find_by_scenario_with_features(version_id)

        # Calculate statistics
        # Note: scenario passed as version, logic adapted below
        stats = self._calculate_version_stats(scenario, builds)

        # Get build status breakdown
        status_breakdown = self._calculate_status_breakdown(builds)

        # Get feature completeness
        feature_completeness = self._calculate_feature_completeness(
            builds, scenario.feature_config.dag_features
        )

        # Get quality scores if available
        # Update DataQualityRepository to support TrainingScenario
        quality_report = self.quality_repo.find_by_scenario(version_id)
        if quality_report and quality_report.status == "completed":
            stats.quality_score = quality_report.quality_score
            stats.completeness_score = quality_report.completeness_score
            stats.validity_score = quality_report.validity_score
            stats.consistency_score = quality_report.consistency_score
            stats.coverage_score = quality_report.coverage_score

        return VersionStatisticsResponse(
            version_id=version_id,
            dataset_id=dataset_id,
            version_name=scenario.name,
            status=(
                scenario.status
                if isinstance(scenario.status, str)
                else scenario.status.value
            ),
            statistics=stats,
            build_status_breakdown=status_breakdown,
            feature_completeness=feature_completeness,
            started_at=scenario.processing_started_at,
            completed_at=scenario.processing_completed_at,
            evaluated_at=None,
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
            dataset_id: Ignored (legacy param) or User ID owner
            version_id: Scenario ID
            features: Optional list of features (defaults to all selected)
            bins: Number of histogram bins for numeric features
            top_n: Max categorical values to return

        Returns:
            FeatureDistributionResponse with distribution data
        """
        scenario = self.scenario_repo.find_by_id(version_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get features to analyze
        target_features = features or scenario.feature_config.dag_features
        if not target_features:
            return FeatureDistributionResponse(version_id=version_id, distributions={})

        # Get all builds with features from FeatureVector (as dicts)
        builds = self.build_repo.find_by_scenario_with_features(version_id)

        distributions: Dict[str, Any] = {}

        for feature_name in target_features:
            # Collect all values for this feature
            values = []
            for build in builds:
                build_features = build.get("features", {})
                if build_features and feature_name in build_features:
                    values.append(build_features[feature_name])

            if not values:
                continue

            # Get data type from registry, fallback to inference
            data_type = get_feature_data_type(feature_name)
            if data_type == "unknown":
                data_type = self._infer_data_type(values)

            if data_type in ("integer", "float"):
                dist = self._calculate_numeric_distribution(
                    feature_name, values, bins=bins
                )
            else:
                dist = self._calculate_categorical_distribution(
                    feature_name, values, top_n=top_n
                )

            distributions[feature_name] = dist.model_dump()

        return FeatureDistributionResponse(
            version_id=version_id, distributions=distributions
        )

    def get_correlation_matrix(
        self,
        dataset_id: str,
        version_id: str,
        features: Optional[List[str]] = None,
    ) -> CorrelationMatrixResponse:
        """
        Calculate correlation matrix between numeric features.

        Args:
            dataset_id: Ignored (legacy param) or User ID owner
            version_id: Scenario ID
            features: Optional list of features (defaults to all numeric)

        Returns:
            CorrelationMatrixResponse with matrix and significant pairs
        """
        scenario = self.scenario_repo.find_by_id(version_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get feature metadata
        all_features = self.feature_service.list_features()
        numeric_features = [
            f["name"]
            for f in all_features
            if f["data_type"] in ("integer", "float", "numeric")
            and f["name"] in (features or scenario.feature_config.dag_features)
        ]

        if not numeric_features:
            return CorrelationMatrixResponse(
                version_id=version_id, features=[], matrix=[], significant_pairs=[]
            )

        # Get all builds with features from FeatureVector (as dicts)
        builds = self.build_repo.find_by_scenario_with_features(version_id)

        # Build value matrix
        feature_values: Dict[str, List[Optional[float]]] = {
            f: [] for f in numeric_features
        }

        for build in builds:
            for feature in numeric_features:
                value = None
                build_features = build.get("features", {})
                if build_features and feature in build_features:
                    try:
                        value = float(build_features[feature])
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
                    corr = self._calculate_correlation(
                        feature_values[f1], feature_values[f2]
                    )
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

    def get_scan_metrics_statistics(
        self,
        dataset_id: str,
        version_id: str,
    ) -> ScanMetricsStatisticsResponse:
        """
        Get aggregated scan metrics statistics for a scenario.

        Aggregates Trivy and SonarQube scan metrics from FeatureVector.scan_metrics.

        Args:
            dataset_id: Ignored (legacy param) or User ID owner
            version_id: Scenario ID

        Returns:
            ScanMetricsStatisticsResponse with Trivy and SonarQube summaries
        """
        scenario = self.scenario_repo.find_by_id(version_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Get all builds with scan_metrics from FeatureVector (as dicts)
        builds = self.build_repo.find_by_scenario_with_features(version_id)

        # Initialize summaries
        scan_summary = ScanSummary(total_builds=len(builds))
        trivy_summary = TrivySummary()
        sonar_summary = SonarSummary()

        # Collect metrics
        trivy_metrics: Dict[str, List[float]] = {
            "vuln_total": [],
            "vuln_critical": [],
            "vuln_high": [],
            "vuln_medium": [],
            "vuln_low": [],
            "misconfig_total": [],
            "misconfig_critical": [],
            "misconfig_high": [],
            "misconfig_medium": [],
            "misconfig_low": [],
            "secrets_count": [],
            "scan_duration_ms": [],
        }

        sonar_metrics: Dict[str, List[float]] = {
            "bugs": [],
            "code_smells": [],
            "vulnerabilities": [],
            "security_hotspots": [],
            "complexity": [],
            "cognitive_complexity": [],
            "duplicated_lines_density": [],
            "ncloc": [],
            "reliability_rating": [],
            "security_rating": [],
            "sqale_rating": [],
        }

        has_critical_count = 0
        has_high_count = 0
        alert_status_ok = 0
        alert_status_error = 0

        for build in builds:
            # Note: "scan_metrics" is flattened in repository aggregation
            scan_metrics = build.get("scan_metrics", {})
            if not scan_metrics:
                continue

            # Check if has Trivy metrics
            has_trivy = any(k.startswith("trivy_") for k in scan_metrics.keys())
            has_sonar = any(k.startswith("sonar_") for k in scan_metrics.keys())

            if has_trivy:
                scan_summary.builds_with_trivy += 1

                # Collect Trivy metrics
                for key, values_list in trivy_metrics.items():
                    metric_key = f"trivy_{key}"
                    if metric_key in scan_metrics:
                        try:
                            val = float(scan_metrics[metric_key])
                            values_list.append(val)
                        except (ValueError, TypeError):
                            pass

                # Check for critical/high
                if scan_metrics.get("trivy_has_critical", False):
                    has_critical_count += 1
                if scan_metrics.get("trivy_has_high", False):
                    has_high_count += 1

            if has_sonar:
                scan_summary.builds_with_sonar += 1

                # Collect SonarQube metrics
                for key, values_list in sonar_metrics.items():
                    metric_key = f"sonar_{key}"
                    if metric_key in scan_metrics:
                        try:
                            val = float(scan_metrics[metric_key])
                            values_list.append(val)
                        except (ValueError, TypeError):
                            pass

                # Alert status
                alert_status = scan_metrics.get("sonar_alert_status", "")
                if alert_status == "OK":
                    alert_status_ok += 1
                elif alert_status in ("ERROR", "WARN"):
                    alert_status_error += 1

            if has_trivy or has_sonar:
                scan_summary.builds_with_any_scan += 1

        # Calculate coverage rates
        if scan_summary.total_builds > 0:
            scan_summary.trivy_coverage_pct = round(
                scan_summary.builds_with_trivy / scan_summary.total_builds * 100, 1
            )
            scan_summary.sonar_coverage_pct = round(
                scan_summary.builds_with_sonar / scan_summary.total_builds * 100, 1
            )

        # Build Trivy summary
        trivy_summary.vuln_total = self._calculate_metric_summary(
            trivy_metrics["vuln_total"]
        )
        trivy_summary.vuln_critical = self._calculate_metric_summary(
            trivy_metrics["vuln_critical"]
        )
        trivy_summary.vuln_high = self._calculate_metric_summary(
            trivy_metrics["vuln_high"]
        )
        trivy_summary.vuln_medium = self._calculate_metric_summary(
            trivy_metrics["vuln_medium"]
        )
        trivy_summary.vuln_low = self._calculate_metric_summary(
            trivy_metrics["vuln_low"]
        )
        trivy_summary.misconfig_total = self._calculate_metric_summary(
            trivy_metrics["misconfig_total"]
        )
        trivy_summary.misconfig_critical = self._calculate_metric_summary(
            trivy_metrics["misconfig_critical"]
        )
        trivy_summary.misconfig_high = self._calculate_metric_summary(
            trivy_metrics["misconfig_high"]
        )
        trivy_summary.misconfig_medium = self._calculate_metric_summary(
            trivy_metrics["misconfig_medium"]
        )
        trivy_summary.misconfig_low = self._calculate_metric_summary(
            trivy_metrics["misconfig_low"]
        )
        trivy_summary.secrets_count = self._calculate_metric_summary(
            trivy_metrics["secrets_count"]
        )
        trivy_summary.scan_duration_ms = self._calculate_metric_summary(
            trivy_metrics["scan_duration_ms"]
        )
        trivy_summary.has_critical_count = has_critical_count
        trivy_summary.has_high_count = has_high_count
        trivy_summary.total_scans = scan_summary.builds_with_trivy

        # Build SonarQube summary
        sonar_summary.bugs = self._calculate_metric_summary(sonar_metrics["bugs"])
        sonar_summary.code_smells = self._calculate_metric_summary(
            sonar_metrics["code_smells"]
        )
        sonar_summary.vulnerabilities = self._calculate_metric_summary(
            sonar_metrics["vulnerabilities"]
        )
        sonar_summary.security_hotspots = self._calculate_metric_summary(
            sonar_metrics["security_hotspots"]
        )
        sonar_summary.complexity = self._calculate_metric_summary(
            sonar_metrics["complexity"]
        )
        sonar_summary.cognitive_complexity = self._calculate_metric_summary(
            sonar_metrics["cognitive_complexity"]
        )
        sonar_summary.duplicated_lines_density = self._calculate_metric_summary(
            sonar_metrics["duplicated_lines_density"]
        )
        sonar_summary.ncloc = self._calculate_metric_summary(sonar_metrics["ncloc"])

        # Ratings
        if sonar_metrics["reliability_rating"]:
            sonar_summary.reliability_rating_avg = round(
                sum(sonar_metrics["reliability_rating"])
                / len(sonar_metrics["reliability_rating"]),
                2,
            )
        if sonar_metrics["security_rating"]:
            sonar_summary.security_rating_avg = round(
                sum(sonar_metrics["security_rating"])
                / len(sonar_metrics["security_rating"]),
                2,
            )
        if sonar_metrics["sqale_rating"]:
            sonar_summary.maintainability_rating_avg = round(
                sum(sonar_metrics["sqale_rating"]) / len(sonar_metrics["sqale_rating"]),
                2,
            )

        sonar_summary.alert_status_ok_count = alert_status_ok
        sonar_summary.alert_status_error_count = alert_status_error
        sonar_summary.total_scans = scan_summary.builds_with_sonar

        return ScanMetricsStatisticsResponse(
            version_id=version_id,
            dataset_id=dataset_id,
            scan_summary=scan_summary,
            trivy_summary=trivy_summary,
            sonar_summary=sonar_summary,
        )

    def _calculate_metric_summary(self, values: List[float]) -> MetricSummary:
        """Calculate summary statistics for a list of metric values."""
        if not values:
            return MetricSummary()

        return MetricSummary(
            sum=round(sum(values), 2),
            avg=round(sum(values) / len(values), 2),
            max=round(max(values), 2),
            min=round(min(values), 2),
            count=len(values),
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
        self, scenario, builds: List[Dict[str, Any]]
    ) -> VersionStatistics:
        """Calculate aggregate scenario statistics."""
        total = len(builds)

        if total == 0:
            return VersionStatistics(
                total_features_selected=len(scenario.feature_config.dag_features or [])
            )

        enriched = sum(
            1 for b in builds if b.get("features") and len(b.get("features", {})) > 0
        )
        failed = sum(1 for b in builds if b.get("extraction_status") == "failed")
        partial = sum(
            1
            for b in builds
            if b.get("features")
            and 0
            < len(b.get("features", {}))
            < len(scenario.feature_config.dag_features or [])
        )

        # Calculate feature stats
        total_features = sum(
            len(b.get("features", {})) for b in builds if b.get("features")
        )
        avg_features = total_features / enriched if enriched > 0 else 0

        # Processing duration
        duration = None
        if scenario.processing_started_at and scenario.processing_completed_at:
            duration = (
                scenario.processing_completed_at - scenario.processing_started_at
            ).total_seconds()

        return VersionStatistics(
            total_builds=total,
            enriched_builds=enriched,
            failed_builds=failed,
            partial_builds=partial,
            enrichment_rate=(enriched / total * 100) if total > 0 else 0,
            success_rate=(
                enriched / (enriched + failed) * 100 if (enriched + failed) > 0 else 0
            ),
            total_features_selected=len(scenario.feature_config.dag_features or []),
            avg_features_per_build=round(avg_features, 2),
            total_feature_values_extracted=total_features,
            processing_duration_seconds=duration,
        )

    def _calculate_status_breakdown(
        self, builds: List[Dict[str, Any]]
    ) -> List[BuildStatusBreakdown]:
        """Calculate build status breakdown."""
        total = len(builds)
        if total == 0:
            return []

        status_counts: Dict[str, int] = Counter()

        for build in builds:
            status = build.get("extraction_status", "pending")
            # Handle if status is Enum in list of dicts (unlikely with aggregate pymongo return, but possible if manual logic used before)
            # PyMongo returns strings for Enum fields stored as values
            status_counts[status] += 1

        return [
            BuildStatusBreakdown(
                status=status,
                count=count,
                percentage=round(count / total * 100, 1),
            )
            for status, count in sorted(
                status_counts.items(), key=lambda x: x[1], reverse=True
            )
        ]

    def _calculate_feature_completeness(
        self, builds: List[Dict[str, Any]], selected_features: List[str]
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
                    completeness_pct=(
                        round(non_null / total * 100, 1) if total > 0 else 0
                    ),
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
        counts = Counter(string_values)
        unique_count = len(counts)

        # Get top N values
        top_values = counts.most_common(top_n)

        categorical_values = [
            CategoricalValue(
                value=val,
                count=count,
                percentage=round(count / len(string_values) * 100, 1),
            )
            for val, count in top_values
        ]

        # Add "Other" category if needed
        if unique_count > top_n:
            shown_count = sum(v.count for v in categorical_values)
            other_count = len(string_values) - shown_count
            categorical_values.append(
                CategoricalValue(
                    value="Other",
                    count=other_count,
                    percentage=round(other_count / len(string_values) * 100, 1),
                )
            )

        return CategoricalDistribution(
            feature_name=feature_name,
            total_count=len(values),
            null_count=null_count,
            unique_count=unique_count,
            values=categorical_values,
        )

    def _calculate_correlation(
        self, values_1: List[Optional[float]], values_2: List[Optional[float]]
    ) -> Optional[float]:
        """Calculate Pearson correlation coefficient."""
        if not values_1 or not values_2 or len(values_1) != len(values_2):
            return None

        # Filter to pairs where both are not None
        v1_clean, v2_clean = [], []
        for x, y in zip(values_1, values_2):
            if x is not None and y is not None:
                v1_clean.append(x)
                v2_clean.append(y)

        if len(v1_clean) < 2:
            return None

        # Check for zero variance
        if len(set(v1_clean)) == 1 or len(set(v2_clean)) == 1:
            return 0.0

        try:
            correlation = statistics.correlation(v1_clean, v2_clean)
            # Clamp to [-1, 1] due to floating point errors
            return round(max(-1, min(1, correlation)), 4)
        except (statistics.StatisticsError, ValueError):
            return None

    def _get_correlation_strength(self, corr: float) -> str:
        """Get human-readable correlation strength."""
        abs_corr = abs(corr)
        if abs_corr >= 0.8:
            return "strong_positive" if corr > 0 else "strong_negative"
        elif abs_corr >= 0.5:
            return "moderate_positive" if corr > 0 else "moderate_negative"
        else:
            return "weak"
