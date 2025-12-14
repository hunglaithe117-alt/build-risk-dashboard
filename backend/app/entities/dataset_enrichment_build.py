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
    raw_workflow_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_workflow_runs table",
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
    dataset_repo_config_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to dataset_repo_configs table",
    )

    # CSV tracking
    build_id_from_csv: str = Field(
        ...,
        description="Original build ID as it appears in CSV",
    )
    csv_row_index: int = Field(
        ...,
        description="Row index in the CSV file (0-based)",
    )
    csv_row_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Original row data from CSV for reference",
    )

    # Build metadata (denormalized for quick access)
    head_sha: Optional[str] = Field(
        None,
        description="Git commit SHA (denormalized from raw_workflow_run)",
    )
    build_number: Optional[int] = Field(
        None,
        description="Build number (denormalized)",
    )
    build_conclusion: Optional[str] = Field(
        None,
        description="Build conclusion: success, failure, etc (denormalized)",
    )
    build_created_at: Optional[datetime] = Field(
        None,
        description="Build creation time (denormalized)",
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

    # ** FEATURES - The actual extracted feature values **
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="""
        Extracted features as key-value pairs.
        This is the main data payload for dataset enrichment.
        """,
        example={
            # Git features
            "files_changed": 5,
            "lines_added": 120,
            "lines_deleted": 45,
            "commits_count": 1,
            # Test features
            "test_cases_total": 150,
            "test_cases_passed": 148,
            "test_cases_failed": 2,
            "test_cases_skipped": 0,
            "test_duration_seconds": 45.2,
            # Code quality
            "complexity_avg": 3.5,
            "complexity_max": 12,
            "code_churn": 165,
            # Build metadata
            "build_duration_seconds": 180,
        },
    )

    # Feature metadata
    feature_count: int = Field(
        default=0,
        description="Number of features extracted",
    )

    # Enrichment tracking
    enriched_at: Optional[datetime] = Field(
        None,
        description="When this build was enriched with features",
    )
    enrichment_attempt: int = Field(
        default=1,
        description="Attempt number (for retry tracking)",
    )
