"""
FeatureVector Entity - Single source of truth for extracted features.

This entity stores features extracted by Hamilton DAG pipeline, shared between:
- Model Training flow (ModelTrainingBuild)
- Dataset Enrichment flow (DatasetEnrichmentBuild)

Key design principles:
- 1:1 relationship with RawBuildRun (unique constraint)
- Stores tr_prev_build for temporal feature chain lookups
- Pure feature storage - no flow-specific metadata
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId
from app.entities.enums import ExtractionStatus, FeatureVectorScope


class FeatureVector(BaseEntity):
    """
    Pure feature storage - single source of truth for Hamilton DAG outputs.

    Indexed by (raw_repo_id, raw_build_run_id, scope, config_id) for uniqueness.
    Referenced by ModelTrainingBuild and DatasetEnrichmentBuild.
    """

    class Config:
        collection = "feature_vectors"
        use_enum_values = True

    # Identity (unique key: raw_repo_id + raw_build_run_id)
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )
    raw_build_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_build_runs table (1:1 relationship)",
    )

    # Scoping (Context)
    scope: FeatureVectorScope = Field(
        default=FeatureVectorScope.MODEL,
        description="Context scope: 'model_training' or 'dataset_enrichment'",
    )
    config_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to configuration (ModelRepoConfig or DatasetVersion)",
    )

    # Version tracking
    dag_version: str = Field(
        default="1.0",
        description="Version of Hamilton DAG used for feature extraction",
    )
    computed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When features were computed",
    )

    # Quick lookup for temporal features (indexed)
    tr_prev_build: Optional[str] = Field(
        None,
        description="CI run ID of previous build in commit chain (for temporal feature lookups)",
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

    # Graceful degradation tracking
    is_missing_commit: bool = Field(
        default=False,
        description="Whether the commit is missing from the repository",
    )
    missing_resources: List[str] = Field(
        default_factory=list,
        description="Resources unavailable during extraction (e.g., 'git_worktree', 'build_logs')",
    )
    skipped_features: List[str] = Field(
        default_factory=list,
        description="Features skipped due to missing resources",
    )

    # ** FEATURES - The actual extracted feature values **
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="DAG extracted features (gh_*, tr_*, git_*, etc.)",
    )
    feature_count: int = Field(
        default=0,
        description="Number of features extracted",
    )

    # ** NORMALIZED FEATURES - Model input features (scaled/standardized) **
    normalized_features: Dict[str, float] = Field(
        default_factory=dict,
        description="Scaled/standardized features for prediction model input. "
        "Contains TEMPORAL_FEATURES + STATIC_FEATURES transformed by the model's scalers.",
    )

    # ** SCAN METRICS - Results from scan tools (backfilled asynchronously) **
    scan_metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scan tool metrics (sonar_*, trivy_*). Backfilled after scan completion.",
    )
