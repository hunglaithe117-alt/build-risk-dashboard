"""
Data Quality Service - Core evaluation logic for dataset quality assessment.

Evaluates enriched datasets and calculates quality scores based on:
- Completeness: % features non-null
- Validity: % values within valid range (from FEATURE_REGISTRY)
- Consistency: % builds with all selected features
- Coverage: % successfully enriched builds

Quality Score Formula:
    quality_score = 0.4 * completeness + 0.3 * validity + 0.2 * consistency + 0.1 * coverage
"""

import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from fastapi import HTTPException
from pymongo.database import Database

from app.entities.data_quality import (
    DataQualityMetric,
    DataQualityReport,
    QualityIssue,
    QualityIssueSeverity,
)
from app.repositories.data_quality_repository import DataQualityRepository
from app.repositories.feature_vector import FeatureVectorRepository
from app.repositories.training_enrichment_build import TrainingEnrichmentBuildRepository
from app.repositories.training_scenario import TrainingScenarioRepository
from app.services.feature_service import FeatureService

logger = logging.getLogger(__name__)


class DataQualityService:
    """Service for evaluating dataset quality."""

    # Score weights
    COMPLETENESS_WEIGHT = 0.4
    VALIDITY_WEIGHT = 0.3
    CONSISTENCY_WEIGHT = 0.2
    COVERAGE_WEIGHT = 0.1

    def __init__(self, db: Database):
        self.db = db
        self.quality_repo = DataQualityRepository(db)
        self.scenario_repo = TrainingScenarioRepository(db)
        self.build_repo = TrainingEnrichmentBuildRepository(db)
        self.feature_vector_repo = FeatureVectorRepository(db)
        self.feature_service = FeatureService()

    def evaluate_version(self, scenario_id: str) -> DataQualityReport:
        """
        Run quality evaluation for a dataset version.

        Args:
            scenario_id: Scenario ID to evaluate

        Returns:
            DataQualityReport with evaluation results
        """
        # Check for existing running evaluation
        existing = self.quality_repo.find_pending_or_running(scenario_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Quality evaluation is already in progress for this scenario",
            )

        # Get scenario
        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Check status (should be PROCESSED before quality check makes sense)
        if scenario.status != "processed" and scenario.status != "completed":
            # Allowed in processed or completed (if re-running)
            pass
            # Or raise error if strict

        report = DataQualityReport(
            scenario_id=ObjectId(scenario_id),
        )
        report.mark_started()

        try:
            # Get all enrichment builds for this scenario
            builds = self.build_repo.find_by_scenario(scenario_id)

            if not builds:
                report.mark_failed("No enrichment builds found for this scenario")
                self.quality_repo.insert_one(report)
                return report

            # Get selected features (DAG features)
            selected_features = scenario.feature_config.dag_features or []

            if not selected_features:
                report.mark_failed("No features configured for this scenario")
                self.quality_repo.insert_one(report)
                return report

            # Get feature metadata for validity checks
            feature_metadata = self._get_feature_metadata(selected_features)

            # Calculate metrics
            report.total_builds = len(builds)
            report.total_features = len(selected_features)

            # Load feature vectors for all builds in batch
            raw_build_run_ids = [
                b.raw_build_run_id for b in builds if b.raw_build_run_id
            ]
            feature_vectors_map = (
                self.feature_vector_repo.find_many_by_raw_build_run_ids(
                    raw_build_run_ids
                )
            )

            # Create a helper class to hold build + features for analysis
            class BuildWithFeatures:
                def __init__(self, build, features):
                    self.build = build
                    self.features = features or {}

            builds_with_features = []
            for build in builds:
                fv = feature_vectors_map.get(str(build.raw_build_run_id))
                features = fv.features if fv else {}
                builds_with_features.append(BuildWithFeatures(build, features))

            # Calculate coverage score
            enriched_builds = [
                b for b in builds_with_features if b.features and len(b.features) > 0
            ]
            partial_builds = [
                b for b in enriched_builds if len(b.features) < len(selected_features)
            ]
            failed_builds = [
                b
                for b in builds_with_features
                if not b.features or len(b.features) == 0
            ]

            report.enriched_builds = len(enriched_builds)
            report.partial_builds = len(partial_builds)
            report.failed_builds = len(failed_builds)

            # Coverage: % successfully enriched builds
            report.coverage_score = (
                (len(enriched_builds) / len(builds) * 100) if builds else 0.0
            )

            # Calculate feature metrics
            report.feature_metrics = self._calculate_feature_metrics(
                builds=enriched_builds,
                selected_features=selected_features,
                feature_metadata=feature_metadata,
            )

            # Calculate completeness score
            report.completeness_score = self._calculate_completeness_score(
                report.feature_metrics
            )

            # Calculate validity score
            report.validity_score = self._calculate_validity_score(
                report.feature_metrics
            )

            # Calculate consistency score
            report.consistency_score = self._calculate_consistency_score(
                builds=enriched_builds,
                selected_features=selected_features,
            )

            # Detect issues
            report.issues = self._detect_issues(
                report=report,
                feature_metrics=report.feature_metrics,
            )
            report.features_with_issues = len(
                [m for m in report.feature_metrics if m.issues]
            )

            # Calculate overall quality score
            quality_score = (
                self.COMPLETENESS_WEIGHT * report.completeness_score
                + self.VALIDITY_WEIGHT * report.validity_score
                + self.CONSISTENCY_WEIGHT * report.consistency_score
                + self.COVERAGE_WEIGHT * report.coverage_score
            )

            report.mark_completed(quality_score)

            logger.info(
                f"Quality evaluation completed for scenario {scenario_id}: "
                f"score={quality_score:.1f}, "
                f"completeness={report.completeness_score:.1f}, "
                f"validity={report.validity_score:.1f}, "
                f"consistency={report.consistency_score:.1f}, "
                f"coverage={report.coverage_score:.1f}"
            )

        except Exception as e:
            logger.error(f"Quality evaluation failed for scenario {scenario_id}: {e}")
            report.mark_failed(str(e))

        # Save report
        self.quality_repo.insert_one(report)
        return report

    def get_report(self, scenario_id: str) -> Optional[DataQualityReport]:
        """Get the latest quality report for a scenario."""
        return self.quality_repo.find_by_scenario(scenario_id)

    def _get_feature_metadata(
        self, selected_features: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get metadata for selected features including valid_range.

        Returns dict: {feature_name: {data_type, valid_range, valid_values, ...}}
        """
        all_features = self.feature_service.list_features()
        metadata = {}

        for feature in all_features:
            feature_name = feature["name"]
            if feature_name in selected_features:
                metadata[feature_name] = {
                    "data_type": feature.get("data_type", "unknown"),
                    "valid_range": feature.get("valid_range"),
                    "valid_values": feature.get("valid_values"),
                }

        return metadata

    def _calculate_feature_metrics(
        self,
        builds: List[Any],  # BuildWithFeatures objects with .features attribute
        selected_features: List[str],
        feature_metadata: Dict[str, Dict[str, Any]],
    ) -> List[DataQualityMetric]:
        """Calculate quality metrics for each feature."""
        metrics = []

        for feature_name in selected_features:
            meta = feature_metadata.get(feature_name, {})
            data_type = meta.get("data_type", "unknown")
            valid_range = meta.get("valid_range")
            valid_values = meta.get("valid_values")

            # Collect all values for this feature
            values = []
            for build in builds:
                if build.features and feature_name in build.features:
                    values.append(build.features[feature_name])
                else:
                    values.append(None)

            # Calculate metrics
            metric = self._analyze_feature_values(
                feature_name=feature_name,
                values=values,
                data_type=data_type,
                valid_range=valid_range,
                valid_values=valid_values,
            )
            metrics.append(metric)

        return metrics

    def _analyze_feature_values(
        self,
        feature_name: str,
        values: List[Any],
        data_type: str,
        valid_range: Optional[Tuple[float, float]] = None,
        valid_values: Optional[List[str]] = None,
    ) -> DataQualityMetric:
        """Analyze values for a single feature and create metric."""
        total = len(values)
        null_count = sum(1 for v in values if v is None)
        non_null_values = [v for v in values if v is not None]

        metric = DataQualityMetric(
            feature_name=feature_name,
            data_type=data_type,
            total_values=total,
            null_count=null_count,
            completeness_pct=(total - null_count) / total * 100 if total > 0 else 0.0,
            expected_range=valid_range,
            expected_values=valid_values,
        )

        if not non_null_values:
            metric.validity_pct = 100.0  # No values to validate
            return metric

        # Numeric analysis
        if data_type in ("integer", "float", "numeric"):
            numeric_values = []
            for v in non_null_values:
                try:
                    numeric_values.append(float(v))
                except (ValueError, TypeError):
                    logger.debug(
                        f"Skipping non-numeric value '{v}' for feature '{feature_name}'"
                    )

            if numeric_values:
                metric.min_value = min(numeric_values)
                metric.max_value = max(numeric_values)
                metric.mean_value = statistics.mean(numeric_values)
                if len(numeric_values) > 1:
                    metric.std_dev = statistics.stdev(numeric_values)

                # Range validation
                if valid_range:
                    min_valid, max_valid = valid_range
                    out_of_range = [
                        v for v in numeric_values if v < min_valid or v > max_valid
                    ]
                    metric.out_of_range_count = len(out_of_range)
                    metric.validity_pct = (
                        (len(numeric_values) - len(out_of_range))
                        / len(numeric_values)
                        * 100
                    )

                    if metric.out_of_range_count > 0:
                        metric.issues.append(
                            f"{metric.out_of_range_count} values outside range "
                            f"[{min_valid}, {max_valid}]"
                        )

        # String analysis
        elif data_type == "string":
            string_values = [str(v) for v in non_null_values]
            metric.unique_count = len(set(string_values))
            metric.empty_string_count = sum(1 for v in string_values if not v.strip())

            # Value validation for categorical
            if valid_values:
                invalid = [v for v in string_values if v not in valid_values]
                metric.invalid_value_count = len(invalid)
                metric.validity_pct = (
                    (len(string_values) - len(invalid)) / len(string_values) * 100
                )

                if metric.invalid_value_count > 0:
                    metric.issues.append(
                        f"{metric.invalid_value_count} values not in allowed list"
                    )

        # Boolean analysis
        elif data_type == "boolean":
            bool_values = [bool(v) for v in non_null_values]
            true_count = sum(bool_values)
            metric.unique_count = (
                2 if true_count > 0 and true_count < len(bool_values) else 1
            )
            metric.validity_pct = 100.0  # All booleans are valid

        # List analysis
        elif data_type == "list":
            metric.unique_count = len({str(v) for v in non_null_values})
            metric.validity_pct = 100.0

        return metric

    def _calculate_completeness_score(self, metrics: List[DataQualityMetric]) -> float:
        """Calculate overall completeness score from feature metrics."""
        if not metrics:
            return 0.0

        return sum(m.completeness_pct for m in metrics) / len(metrics)

    def _calculate_validity_score(self, metrics: List[DataQualityMetric]) -> float:
        """Calculate overall validity score from feature metrics."""
        if not metrics:
            return 0.0

        return sum(m.validity_pct for m in metrics) / len(metrics)

    def _calculate_consistency_score(
        self,
        builds: List[Any],  # BuildWithFeatures objects with .features attribute
        selected_features: List[str],
    ) -> float:
        """
        Calculate consistency score: % builds with all selected features present.
        """
        if not builds or not selected_features:
            return 0.0

        complete_builds = 0
        for build in builds:
            if not build.features:
                continue
            present_features = set(build.features.keys())
            if present_features >= set(selected_features):
                complete_builds += 1

        return (complete_builds / len(builds)) * 100

    def _detect_issues(
        self,
        report: DataQualityReport,
        feature_metrics: List[DataQualityMetric],
    ) -> List[QualityIssue]:
        """Detect quality issues and create issue list."""
        issues: List[QualityIssue] = []

        # Coverage issues
        if report.coverage_score < 50:
            issues.append(
                QualityIssue(
                    severity=QualityIssueSeverity.ERROR,
                    category="coverage",
                    message=f"Low coverage: only {report.coverage_score:.1f}% of builds enriched",
                    details={
                        "enriched": report.enriched_builds,
                        "total": report.total_builds,
                    },
                )
            )
        elif report.coverage_score < 80:
            issues.append(
                QualityIssue(
                    severity=QualityIssueSeverity.WARNING,
                    category="coverage",
                    message=f"Moderate coverage: {report.coverage_score:.1f}% of builds enriched",
                )
            )

        # Completeness issues
        if report.completeness_score < 50:
            issues.append(
                QualityIssue(
                    severity=QualityIssueSeverity.ERROR,
                    category="completeness",
                    message=(
                        f"Low completeness: average {report.completeness_score:.1f}% "
                        "non-null values"
                    ),
                )
            )

        # Feature-level issues
        for metric in feature_metrics:
            # Low completeness for individual features
            if metric.completeness_pct < 30:
                missing_pct = 100 - metric.completeness_pct
                issues.append(
                    QualityIssue(
                        severity=QualityIssueSeverity.WARNING,
                        category="completeness",
                        feature_name=metric.feature_name,
                        message=(
                            f"Feature '{metric.feature_name}' has {metric.null_count} "
                            f"null values ({missing_pct:.1f}% missing)"
                        ),
                    )
                )

            # Range violations
            if metric.out_of_range_count > 0:
                issues.append(
                    QualityIssue(
                        severity=QualityIssueSeverity.WARNING,
                        category="validity",
                        feature_name=metric.feature_name,
                        message=(
                            f"Feature '{metric.feature_name}' has "
                            f"{metric.out_of_range_count} out-of-range values"
                        ),
                        details={"expected_range": metric.expected_range},
                    )
                )

            # Invalid categorical values
            if metric.invalid_value_count > 0:
                issues.append(
                    QualityIssue(
                        severity=QualityIssueSeverity.WARNING,
                        category="validity",
                        feature_name=metric.feature_name,
                        message=(
                            f"Feature '{metric.feature_name}' has "
                            f"{metric.invalid_value_count} invalid values"
                        ),
                    )
                )

        # Consistency issues
        if report.consistency_score < 50:
            issues.append(
                QualityIssue(
                    severity=QualityIssueSeverity.WARNING,
                    category="consistency",
                    message=(
                        f"Low consistency: only {report.consistency_score:.1f}% "
                        "of builds have all features"
                    ),
                )
            )

        return issues
