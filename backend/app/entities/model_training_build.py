"""
ModelTrainingBuild Entity - Build for ML model training.

This entity tracks builds in the model training flow.
Features are stored in FeatureVector (referenced by feature_vector_id).

Key design principles:
- References FeatureVector for feature storage (single source of truth)
- Stores prediction results and metadata
- Lightweight tracking entity
"""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId
from app.entities.enums import ExtractionStatus


class ModelTrainingBuild(BaseEntity):
    """
    Build tracking for ML model training flow.

    Features are stored in FeatureVector entity, referenced by feature_vector_id.
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

    model_repo_config_id: PyObjectId = Field(
        ...,
        description="Reference to model_repo_configs",
    )
    # Import session reference (via ModelImportBuild)
    model_import_build_id: PyObjectId = Field(
        ...,
        description="Reference to model_import_builds",
    )

    # ** FEATURE VECTOR REFERENCE (single source of truth) **
    feature_vector_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to feature_vectors table (stores extracted features)",
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

    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING,
        description="Feature extraction status",
    )
    extraction_error: Optional[str] = Field(
        None,
        description="Error message if extraction failed",
    )
    extraction_started_at: Optional[datetime] = Field(
        None,
        description="When feature extraction started",
    )
    extracted_at: Optional[datetime] = Field(
        None,
        description="When feature extraction completed",
    )

    # Ground truth label (for supervised learning)
    label: Optional[str] = Field(
        None,
        description="Ground truth label (e.g., 'pass', 'fail', 'LOW', 'MEDIUM', 'HIGH')",
    )

    # Prediction results from Bayesian model
    prediction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING,
        description="Prediction status: PENDING, IN_PROGRESS, COMPLETED, FAILED",
    )
    predicted_label: Optional[str] = Field(
        None,
        description="Predicted risk level (LOW, MEDIUM, HIGH)",
    )
    prediction_confidence: Optional[float] = Field(
        None,
        description="Risk score from prediction model (0-1)",
    )
    prediction_uncertainty: Optional[float] = Field(
        None,
        description="Bayesian uncertainty score",
    )
    prediction_model_version: Optional[str] = Field(
        None,
        description="Version of the prediction model used",
    )
    predicted_at: Optional[datetime] = Field(
        None,
        description="When the prediction was made",
    )
    prediction_error: Optional[str] = Field(
        None,
        description="Error message if prediction failed",
    )
