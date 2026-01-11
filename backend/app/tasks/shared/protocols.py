"""
Pipeline Protocol - Defines interface for pipeline contexts.

This module provides a Protocol class that defines what a pipeline context
must provide for shared tasks to work correctly.
"""

from typing import Any, Dict, List, Optional, Protocol, TypeVar, runtime_checkable


@runtime_checkable
class PipelineContext(Protocol):
    """
    Protocol defining what a pipeline must provide to shared tasks.

    Implementations:
    - ModelPipelineContext: For Model Training pipeline
    - TrainingPipelineContext: For Training Scenario pipeline
    """

    @property
    def pipeline_id(self) -> str:
        """Unique identifier for this pipeline instance (repo_config_id or scenario_id)."""
        ...

    @property
    def pipeline_type(self) -> str:
        """Type identifier: 'model' or 'training'."""
        ...

    @property
    def correlation_id(self) -> str:
        """Correlation ID for distributed tracing."""
        ...

    def get_import_build_repo(self, db: Any) -> Any:
        """Get repository for import/ingestion build records."""
        ...

    def get_enrichment_build_repo(self, db: Any) -> Optional[Any]:
        """Get repository for enrichment build records (Training only)."""
        ...

    def get_config_repo(self, db: Any) -> Any:
        """Get repository for pipeline config (ModelRepoConfig or TrainingScenario)."""
        ...

    def update_resource_status(
        self,
        db: Any,
        build_id: str,
        resource: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update resource status for a build."""
        ...

    def mark_build_ingested(self, db: Any, build_id: str) -> None:
        """Mark a build as INGESTED."""
        ...

    def mark_build_failed(self, db: Any, build_id: str, error: str) -> None:
        """Mark a build as FAILED with error message."""
        ...

    def publish_status(self, status: str, message: str, **kwargs) -> None:
        """Publish status update via WebSocket."""
        ...

    def publish_build_update(self, build_id: str, status: str, **kwargs) -> None:
        """Publish individual build update via WebSocket."""
        ...

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dict for Celery task passing."""
        ...

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineContext":
        """Deserialize context from dict."""
        ...


# Type variable for generic context operations
T = TypeVar("T", bound=PipelineContext)
