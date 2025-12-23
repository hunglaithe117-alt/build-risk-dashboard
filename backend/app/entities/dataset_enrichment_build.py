"""
DatasetEnrichmentBuild Entity - Build for dataset enrichment.

This entity stores extracted features from builds for dataset enrichment.
It's optimized for the dataset enrichment flow with CSV tracking.

Key design principles:
- Dataset enrichment specific: Only fields relevant for enrichment
- CSV tracking: Links back to original CSV rows
- Lightweight: Optimized for dataset export
- References raw data: Links to raw_repository and raw_workflow_run
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId
from app.entities.enums import ExtractionStatus


class DatasetEnrichmentBuild(BaseEntity):
    """
    Build with extracted features for dataset enrichment.

    This entity stores features extracted from builds discovered in
    uploaded datasets, with tracking back to original CSV rows.
    """

    class Config:
        collection = "dataset_enrichment_builds"
        use_enum_values = True

    # References to raw data
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )
    raw_build_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_build_run table",
    )

    # Dataset references
    dataset_id: PyObjectId = Field(
        ...,
        description="Reference to datasets table",
    )
    dataset_version_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to dataset_versions table (if versioned enrichment)",
    )
    dataset_build_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to dataset_builds table",
    )

    # Extraction status
    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING,
        description="Feature extraction status",
    )
    extraction_error: Optional[str] = Field(
        None,
        description="Error message if extraction failed",
    )
    is_missing_commit: bool = Field(
        default=False,
        description="Whether the commit is missing from the repository",
    )
    missing_resources: list = Field(
        default_factory=list,
        description="Resources unavailable during extraction (e.g., 'git_worktree', 'build_logs')",
    )
    skipped_features: list = Field(
        default_factory=list,
        description="Features skipped due to missing resources",
    )

    # ** DAG FEATURES - Features extracted by Hamilton pipeline **
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="DAG extracted features (gh_*, tr_*, etc.). Main pipeline output.",
    )

    # ** SCAN METRICS - Results from scan tools (backfilled asynchronously) **
    scan_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scan tool metrics (sonar_*, trivy_*). Backfilled after scan completion.",
    )

    # Feature metadata - counts ONLY DAG features (not scan metrics)
    feature_count: int = Field(
        default=0,
        description="Number of DAG features extracted",
    )

    enriched_at: Optional[datetime] = Field(
        None,
        description="Timestamp when features were extracted",
    )
