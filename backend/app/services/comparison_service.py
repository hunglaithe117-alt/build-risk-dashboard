"""Service for dataset comparison operations."""

import logging
from typing import List, Set, Tuple

import pandas as pd
from bson import ObjectId
from fastapi import HTTPException, UploadFile
from pymongo.database import Database

from app.dtos.comparison import (
    CompareExternalResponse,
    CompareInternalRequest,
    CompareResponse,
    ExternalDatasetSummary,
    FeatureComparison,
    FeatureComparisonItem,
    QualityComparison,
    RowOverlap,
    VersionSummary,
)
from app.entities.dataset_version import DatasetVersion
from app.repositories.dataset_version import DatasetVersionRepository

logger = logging.getLogger(__name__)


class ComparisonService:
    """Service for comparing datasets and versions."""

    def __init__(self, db: Database):
        self._db = db
        self._version_repo = DatasetVersionRepository(db)

    def compare_internal(self, request: CompareInternalRequest) -> CompareResponse:
        """Compare two internal dataset versions."""
        # Get base version
        base_version = self._version_repo.find_by_id(ObjectId(request.base_version_id))
        if not base_version or str(base_version.dataset_id) != request.base_dataset_id:
            raise HTTPException(status_code=404, detail="Base version not found")

        # Get target version
        target_version = self._version_repo.find_by_id(ObjectId(request.target_version_id))
        if not target_version or str(target_version.dataset_id) != request.target_dataset_id:
            raise HTTPException(status_code=404, detail="Target version not found")

        # Get dataset names
        base_dataset = self._db["datasets"].find_one({"_id": ObjectId(request.base_dataset_id)})
        target_dataset = self._db["datasets"].find_one({"_id": ObjectId(request.target_dataset_id)})

        # Build summaries
        base_summary = self._build_version_summary(
            base_version,
            base_dataset.get("name", "Unknown") if base_dataset else "Unknown",
        )
        target_summary = self._build_version_summary(
            target_version,
            target_dataset.get("name", "Unknown") if target_dataset else "Unknown",
        )

        # Compare features
        feature_comparison = self._compare_features(
            set(base_version.selected_features),
            set(target_version.selected_features),
            request.base_version_id,
            request.target_version_id,
        )

        # Compare quality
        quality_comparison = self._compare_quality(
            request.base_version_id, request.target_version_id
        )

        # Calculate row overlap
        row_overlap = self._calculate_row_overlap(
            request.base_version_id, request.target_version_id
        )

        return CompareResponse(
            comparison_type="internal",
            base=base_summary,
            target=target_summary,
            feature_comparison=feature_comparison,
            quality_comparison=quality_comparison,
            row_overlap=row_overlap,
        )

    def compare_external(
        self,
        version_id: str,
        dataset_id: str,
        file: UploadFile,
    ) -> CompareExternalResponse:
        """Compare an internal version with an uploaded external CSV."""
        # Get internal version
        version = self._version_repo.find_by_id(ObjectId(version_id))
        if not version or str(version.dataset_id) != dataset_id:
            raise HTTPException(status_code=404, detail="Version not found")

        dataset = self._db["datasets"].find_one({"_id": ObjectId(dataset_id)})

        # Parse uploaded CSV
        try:
            df = pd.read_csv(file.file)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

        external_columns = set(df.columns.tolist())
        internal_features = set(version.selected_features)

        # Build summaries
        base_summary = self._build_version_summary(
            version, dataset.get("name", "Unknown") if dataset else "Unknown"
        )

        external_summary = ExternalDatasetSummary(
            filename=file.filename or "uploaded.csv",
            total_rows=len(df),
            total_columns=len(df.columns),
            columns=df.columns.tolist(),
        )

        # Compare features
        common = internal_features & external_columns
        base_only = internal_features - external_columns
        target_only = external_columns - internal_features

        feature_comparison = FeatureComparison(
            common_features=sorted(list(common)),
            base_only_features=sorted(list(base_only)),
            target_only_features=sorted(list(target_only)),
            feature_details=[],
        )

        # Calculate quality for external
        external_null_pct = (df.isnull().sum().sum() / df.size * 100) if df.size > 0 else 0
        base_quality = self._get_version_quality(version_id)

        quality_comparison = QualityComparison(
            base_completeness_pct=base_quality[0],
            target_completeness_pct=100 - external_null_pct,
            base_avg_null_pct=base_quality[1],
            target_avg_null_pct=external_null_pct,
            completeness_diff=(100 - external_null_pct) - base_quality[0],
        )

        return CompareExternalResponse(
            comparison_type="external",
            base=base_summary,
            external_target=external_summary,
            feature_comparison=feature_comparison,
            quality_comparison=quality_comparison,
        )

    def _build_version_summary(self, version: DatasetVersion, dataset_name: str) -> VersionSummary:
        """Build version summary for comparison."""
        completeness = 0.0
        if version.total_rows > 0:
            completeness = (version.enriched_rows / version.total_rows) * 100

        return VersionSummary(
            dataset_id=str(version.dataset_id),
            dataset_name=dataset_name,
            version_id=str(version.id),
            version_name=version.name or f"v{version.version_number}",
            total_rows=version.total_rows,
            total_features=len(version.selected_features),
            selected_features=version.selected_features,
            enriched_rows=version.enriched_rows,
            completeness_pct=round(completeness, 2),
        )

    def _compare_features(
        self,
        base_features: Set[str],
        target_features: Set[str],
        base_version_id: str,
        target_version_id: str,
    ) -> FeatureComparison:
        """Compare features between two versions."""
        common = base_features & target_features
        base_only = base_features - target_features
        target_only = target_features - base_features

        # Build detailed comparison for common features
        details: List[FeatureComparisonItem] = []
        for feature in sorted(common):
            details.append(
                FeatureComparisonItem(
                    feature_name=feature,
                    in_base=True,
                    in_target=True,
                )
            )

        return FeatureComparison(
            common_features=sorted(list(common)),
            base_only_features=sorted(list(base_only)),
            target_only_features=sorted(list(target_only)),
            feature_details=details,
        )

    def _compare_quality(self, base_version_id: str, target_version_id: str) -> QualityComparison:
        """Compare quality metrics between versions."""
        base_quality = self._get_version_quality(base_version_id)
        target_quality = self._get_version_quality(target_version_id)

        return QualityComparison(
            base_completeness_pct=base_quality[0],
            target_completeness_pct=target_quality[0],
            base_avg_null_pct=base_quality[1],
            target_avg_null_pct=target_quality[1],
            completeness_diff=target_quality[0] - base_quality[0],
        )

    def _get_version_quality(self, version_id: str) -> Tuple[float, float]:
        """Get completeness and null percentage for a version."""
        # Check quality reports first
        report = self._db["quality_reports"].find_one(
            {"version_id": version_id, "status": "completed"}
        )
        if report:
            return (
                report.get("completeness_score", 0) * 100,
                100 - report.get("completeness_score", 0) * 100,
            )

        # Fallback: calculate from enrichment builds
        builds = list(
            self._db["enrichment_builds"].find({"dataset_version_id": ObjectId(version_id)})
        )
        if not builds:
            return (0.0, 100.0)

        total_features = 0
        null_features = 0
        for build in builds:
            features = build.get("features", {})
            for value in features.values():
                total_features += 1
                if value is None:
                    null_features += 1

        if total_features == 0:
            return (0.0, 100.0)

        null_pct = (null_features / total_features) * 100
        return (100 - null_pct, null_pct)

    def _calculate_row_overlap(self, base_version_id: str, target_version_id: str) -> RowOverlap:
        """Calculate row overlap between two versions by commit_sha."""
        # Get commit SHAs for each version
        base_shas = set(
            doc["commit_sha"]
            for doc in self._db["enrichment_builds"].find(
                {"dataset_version_id": ObjectId(base_version_id)}, {"commit_sha": 1}
            )
            if doc.get("commit_sha")
        )

        target_shas = set(
            doc["commit_sha"]
            for doc in self._db["enrichment_builds"].find(
                {"dataset_version_id": ObjectId(target_version_id)}, {"commit_sha": 1}
            )
            if doc.get("commit_sha")
        )

        overlapping = base_shas & target_shas
        base_total = len(base_shas)
        target_total = len(target_shas)
        overlap_count = len(overlapping)

        # Calculate overlap percentage (relative to smaller set)
        min_size = min(base_total, target_total) if base_total and target_total else 1
        overlap_pct = (overlap_count / min_size) * 100 if min_size > 0 else 0

        return RowOverlap(
            base_total_rows=base_total,
            target_total_rows=target_total,
            overlapping_rows=overlap_count,
            overlap_pct=round(overlap_pct, 2),
            base_only_rows=len(base_shas - target_shas),
            target_only_rows=len(target_shas - base_shas),
        )
