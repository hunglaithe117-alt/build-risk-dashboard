"""
Statistics API - Endpoints for dataset version statistics and distributions.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.database.mongo import get_db
from app.dtos.scan_statistics import ScanMetricsStatisticsResponse
from app.dtos.statistics import (
    CorrelationMatrixResponse,
    FeatureDistributionResponse,
    VersionStatisticsResponse,
)
from app.middleware.rbac import Permission, RequirePermission
from app.services.statistics_service import StatisticsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/datasets/{dataset_id}/versions/{version_id}/statistics",
    tags=["Statistics"],
)


@router.get("", response_model=VersionStatisticsResponse)
async def get_version_statistics(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get comprehensive statistics for a dataset version.

    Returns:
    - Build counts and rates (total, enriched, failed, partial)
    - Feature extraction statistics
    - Quality scores (if evaluated)
    - Build status breakdown
    - Per-feature completeness metrics
    """
    service = StatisticsService(db)
    return service.get_version_statistics(dataset_id, version_id)


@router.get("/distributions", response_model=FeatureDistributionResponse)
async def get_feature_distributions(
    dataset_id: str,
    version_id: str,
    features: Optional[List[str]] = Query(
        None, description="Features to analyze (defaults to all selected)"
    ),
    bins: int = Query(20, ge=5, le=50, description="Number of histogram bins"),
    top_n: int = Query(
        20, ge=5, le=100, description="Max categorical values to return"
    ),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get value distributions for features.

    For numeric features: Returns histogram bins with counts.
    For categorical features: Returns top N value counts.

    Use this data for:
    - Histograms
    - Bar charts
    - Boxplot overlays (using stats.q1, median, q3)
    """
    service = StatisticsService(db)
    return service.get_feature_distributions(
        dataset_id=dataset_id,
        version_id=version_id,
        features=features,
        bins=bins,
        top_n=top_n,
    )


@router.get("/correlation", response_model=CorrelationMatrixResponse)
async def get_correlation_matrix(
    dataset_id: str,
    version_id: str,
    features: Optional[List[str]] = Query(
        None, description="Numeric features to include (defaults to all numeric)"
    ),
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get Pearson correlation matrix between numeric features.

    Returns:
    - Feature names in order
    - 2D correlation matrix (values from -1 to 1)
    - List of significant pairs (|correlation| >= 0.5)

    Use this for:
    - Heatmap visualization
    - Identifying multicollinearity
    - Feature selection
    """
    service = StatisticsService(db)
    return service.get_correlation_matrix(
        dataset_id=dataset_id,
        version_id=version_id,
        features=features,
    )


@router.get("/scans", response_model=ScanMetricsStatisticsResponse)
async def get_scan_metrics_statistics(
    dataset_id: str,
    version_id: str,
    db=Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Get aggregated scan metrics statistics for a dataset version.

    Returns:
    - Scan summary (coverage rates)
    - Trivy summary (vulnerabilities, misconfigurations, secrets)
    - SonarQube summary (bugs, code smells, security hotspots, complexity)

    Use this for:
    - Security dashboard visualization
    - Quality gate monitoring
    - Trend analysis
    """
    service = StatisticsService(db)
    return service.get_scan_metrics_statistics(
        dataset_id=dataset_id,
        version_id=version_id,
    )
