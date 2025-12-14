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
    raw_workflow_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_workflow_runs table",
    )

    # Config reference
    model_repo_config_id: PyObjectId = Field(
        ...,
        description="Reference to model_repo_configs table",
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
        This is the main data payload for ML training.
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
