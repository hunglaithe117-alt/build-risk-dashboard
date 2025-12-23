"""
Feature Audit Log Entity - Tracks execution history of feature extraction pipelines.

This entity stores comprehensive information about each pipeline execution,
enabling monitoring, debugging, and analytics.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field

from .base import BaseEntity, PyObjectId


class AuditLogCategory(str, Enum):
    """Audit log category."""

    MODEL_TRAINING = "model_training"
    DATASET_ENRICHMENT = "dataset_enrichment"


class FeatureAuditLogStatus(str, Enum):
    """Feature audit log status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeExecutionStatus(str, Enum):
    """Node execution status."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeExecutionResult(BaseEntity):
    """Result of a single node execution within a pipeline run."""

    node_name: str
    status: NodeExecutionStatus = NodeExecutionStatus.SUCCESS
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    features_extracted: List[str] = Field(default_factory=list)

    # NEW: Feature-level tracking for quality evaluation
    feature_values: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted feature values for audit trail",
    )

    # NEW: Resource tracking
    resources_used: List[str] = Field(
        default_factory=list,
        description="Resources used for extraction (git_worktree, github_api, etc.)",
    )
    resources_missing: List[str] = Field(
        default_factory=list,
        description="Resources that were unavailable",
    )

    error: Optional[str] = None
    warning: Optional[str] = None
    skip_reason: Optional[str] = Field(None, description="Reason for skipping if status is SKIPPED")
    retry_count: int = 0

    class Config:
        # Override to not require _id for embedded documents
        populate_by_name = True
        arbitrary_types_allowed = True
        use_enum_values = True


class FeatureAuditLog(BaseEntity):
    """
    Track a single pipeline execution.

    This entity provides complete observability into pipeline runs:
    - What was executed and when
    - Which nodes succeeded/failed
    - Performance metrics (duration, retry counts)
    - Feature extraction results

    References:
    - raw_repo_id -> RawRepository
    - raw_build_run_id -> RawBuildRun
    - training_build_id -> ModelTrainingBuild (for MODEL_TRAINING category)
    - enrichment_build_id -> DatasetEnrichmentBuild (for DATASET_ENRICHMENT category)
    """

    class Config:
        collection = "feature_audit_logs"
        use_enum_values = True

    # === Correlation ID for tracing ===
    correlation_id: Optional[str] = Field(
        None,
        description="Correlation ID for end-to-end tracing via logs",
    )

    # Audit log category
    category: AuditLogCategory = Field(
        default=AuditLogCategory.MODEL_TRAINING,
        description="Type of pipeline: model_training or dataset_enrichment",
    )

    # References to raw data
    raw_repo_id: PyObjectId = Field(
        ...,
        description="Reference to raw_repositories table",
    )
    raw_build_run_id: PyObjectId = Field(
        ...,
        description="Reference to raw_build_runs table",
    )

    # Output entity reference (one of these will be populated based on category)
    training_build_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to model_training_builds (for MODEL_TRAINING)",
    )
    enrichment_build_id: Optional[PyObjectId] = Field(
        None,
        description="Reference to dataset_enrichment_builds (for DATASET_ENRICHMENT)",
    )

    # Direct references for easier querying (denormalized from enrichment_build)
    version_id: Optional[PyObjectId] = Field(
        None,
        description="DatasetVersion ID (for DATASET_ENRICHMENT category)",
    )
    dataset_id: Optional[PyObjectId] = Field(
        None,
        description="Dataset ID (for DATASET_ENRICHMENT category)",
    )

    # Execution metadata
    status: FeatureAuditLogStatus = FeatureAuditLogStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    # Node-level results
    node_results: List[NodeExecutionResult] = Field(default_factory=list)

    # Feature extraction summary
    feature_count: int = 0
    features_extracted: List[str] = Field(default_factory=list)

    # Error tracking
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Node execution counts
    nodes_executed: int = 0
    nodes_succeeded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0

    # Retry tracking
    total_retries: int = 0

    def mark_started(self) -> "FeatureAuditLog":
        """Mark audit log as started."""
        self.status = FeatureAuditLogStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        return self

    def mark_completed(self, features: List[str]) -> "FeatureAuditLog":
        """Mark audit log as successfully completed."""
        self.status = FeatureAuditLogStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.features_extracted = features
        self.feature_count = len(features)
        self._update_node_counts()
        return self

    def mark_failed(self, error: str) -> "FeatureAuditLog":
        """Mark audit log as failed."""
        self.status = FeatureAuditLogStatus.FAILED
        self.completed_at = datetime.now(timezone.utc)
        if self.started_at:
            self.duration_ms = (self.completed_at - self.started_at).total_seconds() * 1000
        self.errors.append(error)
        self._update_node_counts()
        return self

    def add_node_result(self, result: NodeExecutionResult) -> None:
        """Add a node execution result."""
        self.node_results.append(result)
        self.total_retries += result.retry_count

    def _update_node_counts(self) -> None:
        """Update node execution counts from results."""
        self.nodes_executed = len(self.node_results)
        self.nodes_succeeded = sum(1 for r in self.node_results if r.status == "success")
        self.nodes_failed = sum(1 for r in self.node_results if r.status == "failed")
        self.nodes_skipped = sum(1 for r in self.node_results if r.status == "skipped")
