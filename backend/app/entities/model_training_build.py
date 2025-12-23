"""
ModelTrainingBuild Entity - Build for ML model training.

This entity stores extracted features from builds used for ML model training.
It's optimized for the model training flow with relevant fields.

Key design principles:
- Model training specific: Only fields relevant for ML training
- Lightweight: Optimized for feature extraction and model input
- References raw data: Links to raw_repository and raw_workflow_run
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId
from app.entities.enums import ExtractionStatus


class ModelTrainingBuild(BaseEntity):
    """
    Build with extracted features for ML model training.

    This entity stores features extracted from builds for training
    build failure prediction models.
    """

    class Config:
        collection = "model_training_builds"
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

    # Import session reference (via ModelImportBuild)
    model_import_build_id: PyObjectId = Field(
        ...,
        description="Reference to model_import_builds",
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
    missing_resources: list = Field(
        default_factory=list,
        description="Resources unavailable during extraction (e.g., 'git_worktree', 'build_logs')",
    )
    skipped_features: list = Field(
        default_factory=list,
        description="Features skipped due to missing resources",
    )

    # ** FEATURES - The actual extracted feature values **
    features: Dict[str, Any] = Field(
        default_factory=dict,
        description="""
        Extracted features as key-value pairs.
        This is the main data payload for ML training.
        """,
    )

    # Feature metadata
    feature_count: int = Field(
        default=0,
        description="Number of features extracted",
    )

    # ML-specific fields
    is_labeled: bool = Field(
        default=False,
        description="Whether this build has been labeled for training",
    )
    label: Optional[str] = Field(
        None,
        description="Label for supervised learning (e.g., 'pass', 'fail')",
    )
    in_training_set: bool = Field(
        default=False,
        description="Whether this build is included in training set",
    )
    in_test_set: bool = Field(
        default=False,
        description="Whether this build is included in test set",
    )

    # Prediction tracking (if model has been applied)
    has_prediction: bool = Field(
        default=False,
        description="Whether a prediction exists for this build",
    )
    predicted_label: Optional[str] = Field(
        None,
        description="Predicted label from the model",
    )
    prediction_confidence: Optional[float] = Field(
        None,
        description="Confidence score of the prediction (0-1)",
    )
    predicted_at: Optional[datetime] = Field(
        None,
        description="When the prediction was made",
    )
