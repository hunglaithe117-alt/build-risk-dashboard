"""
Pipeline Run Entity - Tracks execution history of feature extraction pipelines.

This entity stores comprehensive information about each pipeline execution,
enabling monitoring, debugging, and analytics.
"""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import Field

from .base import BaseEntity, PyObjectId


class NodeExecutionResult(BaseEntity):
    """Result of a single node execution within a pipeline run."""

    node_name: str
    status: str  # "success", "failed", "skipped"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    features_extracted: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None
    retry_count: int = 0

    class Config:
        # Override to not require _id for embedded documents
        populate_by_name = True
        arbitrary_types_allowed = True


class PipelineRun(BaseEntity):
    """
    Track a single pipeline execution.

    This entity provides complete observability into pipeline runs:
    - What was executed and when
    - Which nodes succeeded/failed
    - Performance metrics (duration, retry counts)
    - Feature extraction results
    """

    # References
    build_sample_id: PyObjectId
    repo_id: PyObjectId
    workflow_run_id: int

    # Execution metadata
    status: str = "pending"  # "pending", "running", "completed", "failed", "cancelled"
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

    # DAG metadata
    dag_version: Optional[str] = None  # Hash of DAG structure for versioning
    nodes_requested: int = 0
    nodes_executed: int = 0
    nodes_succeeded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0

    # Retry tracking
    total_retries: int = 0

    def mark_started(self) -> "PipelineRun":
        """Mark pipeline as started."""
        self.status = "running"
        self.started_at = datetime.now(timezone.utc)
        return self

    def mark_completed(self, features: List[str]) -> "PipelineRun":
        """Mark pipeline as successfully completed."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000
        self.features_extracted = features
        self.feature_count = len(features)
        self._update_node_counts()
        return self

    def mark_failed(self, error: str) -> "PipelineRun":
        """Mark pipeline as failed."""
        self.status = "failed"
        self.completed_at = datetime.now(timezone.utc)
        if self.started_at:
            self.duration_ms = (
                self.completed_at - self.started_at
            ).total_seconds() * 1000
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
        self.nodes_succeeded = sum(
            1 for r in self.node_results if r.status == "success"
        )
        self.nodes_failed = sum(1 for r in self.node_results if r.status == "failed")
        self.nodes_skipped = sum(1 for r in self.node_results if r.status == "skipped")
