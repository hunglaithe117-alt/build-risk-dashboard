"""
Pipeline Contexts - Concrete implementations of PipelineContext protocol.

This module provides context classes for each pipeline type:
- ModelPipelineContext: For Model Training pipeline
- TrainingPipelineContext: For Training Scenario pipeline
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ModelPipelineContext:
    """
    Context for Model Training pipeline.

    Used when processing builds for risk prediction model training.
    """

    repo_config_id: str
    correlation_id: str = ""
    _raw_repo_id: Optional[str] = field(default=None, repr=False)
    _github_repo_id: Optional[int] = field(default=None, repr=False)
    _full_name: Optional[str] = field(default=None, repr=False)

    @property
    def pipeline_id(self) -> str:
        return self.repo_config_id

    @property
    def pipeline_type(self) -> str:
        return "model"

    def get_import_build_repo(self, db: Any) -> Any:
        from app.repositories.model_import_build import ModelImportBuildRepository

        return ModelImportBuildRepository(db)

    def get_enrichment_build_repo(self, db: Any) -> Optional[Any]:
        # Model pipeline doesn't use enrichment builds
        return None

    def get_config_repo(self, db: Any) -> Any:
        from app.repositories.model_repo_config import ModelRepoConfigRepository

        return ModelRepoConfigRepository(db)

    def update_resource_status(
        self,
        db: Any,
        build_id: str,
        resource: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        from app.repositories.model_import_build import ModelImportBuildRepository

        repo = ModelImportBuildRepository(db)
        repo.update_resource_status(build_id, resource, status, error)

    def mark_build_ingested(self, db: Any, build_id: str) -> None:
        from app.entities.model_import_build import ModelImportBuildStatus
        from app.repositories.model_import_build import ModelImportBuildRepository

        repo = ModelImportBuildRepository(db)
        repo.update_one(build_id, {"status": ModelImportBuildStatus.INGESTED.value})

    def mark_build_failed(self, db: Any, build_id: str, error: str) -> None:
        from app.entities.model_import_build import ModelImportBuildStatus
        from app.repositories.model_import_build import ModelImportBuildRepository

        repo = ModelImportBuildRepository(db)
        repo.update_one(
            build_id,
            {
                "status": ModelImportBuildStatus.FAILED.value,
                "ingestion_error": error,
            },
        )

    def publish_status(self, status: str, message: str, **kwargs) -> None:
        from app.tasks.shared.events import publish_status

        publish_status(self.repo_config_id, status, message, **kwargs)

    def publish_build_update(self, build_id: str, status: str, **kwargs) -> None:
        from app.tasks.shared.events import publish_ingestion_build_update

        publish_ingestion_build_update(
            self.repo_config_id,
            build_id,
            status,
            pipeline_type="model",
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "model",
            "repo_config_id": self.repo_config_id,
            "correlation_id": self.correlation_id,
            "raw_repo_id": self._raw_repo_id,
            "github_repo_id": self._github_repo_id,
            "full_name": self._full_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelPipelineContext":
        return cls(
            repo_config_id=data["repo_config_id"],
            correlation_id=data.get("correlation_id", ""),
            _raw_repo_id=data.get("raw_repo_id"),
            _github_repo_id=data.get("github_repo_id"),
            _full_name=data.get("full_name"),
        )


@dataclass
class TrainingPipelineContext:
    """
    Context for Training Scenario pipeline.

    Used when processing builds for dataset enrichment in training scenarios.
    """

    scenario_id: str
    correlation_id: str = ""
    _raw_repo_id: Optional[str] = field(default=None, repr=False)
    _github_repo_id: Optional[int] = field(default=None, repr=False)
    _full_name: Optional[str] = field(default=None, repr=False)

    @property
    def pipeline_id(self) -> str:
        return self.scenario_id

    @property
    def pipeline_type(self) -> str:
        return "training"

    def get_import_build_repo(self, db: Any) -> Any:
        from app.repositories.training_ingestion_build import (
            TrainingIngestionBuildRepository,
        )

        return TrainingIngestionBuildRepository(db)

    def get_enrichment_build_repo(self, db: Any) -> Any:
        from app.repositories.training_enrichment_build import (
            TrainingEnrichmentBuildRepository,
        )

        return TrainingEnrichmentBuildRepository(db)

    def get_config_repo(self, db: Any) -> Any:
        from app.repositories.training_scenario import TrainingScenarioRepository

        return TrainingScenarioRepository(db)

    def update_resource_status(
        self,
        db: Any,
        build_id: str,
        resource: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        from app.repositories.training_ingestion_build import (
            TrainingIngestionBuildRepository,
        )

        repo = TrainingIngestionBuildRepository(db)
        repo.update_resource_status(build_id, resource, status, error)

    def mark_build_ingested(self, db: Any, build_id: str) -> None:
        from app.entities.training_ingestion_build import IngestionBuildStatus
        from app.repositories.training_ingestion_build import (
            TrainingIngestionBuildRepository,
        )

        repo = TrainingIngestionBuildRepository(db)
        repo.update_one(build_id, {"status": IngestionBuildStatus.INGESTED.value})

    def mark_build_failed(self, db: Any, build_id: str, error: str) -> None:
        from app.entities.training_ingestion_build import IngestionBuildStatus
        from app.repositories.training_ingestion_build import (
            TrainingIngestionBuildRepository,
        )

        repo = TrainingIngestionBuildRepository(db)
        repo.update_one(
            build_id,
            {
                "status": IngestionBuildStatus.FAILED.value,
                "ingestion_error": error,
            },
        )

    def publish_status(self, status: str, message: str, **kwargs) -> None:
        from app.tasks.shared.events import publish_scenario_update

        publish_scenario_update(self.scenario_id, status, message, **kwargs)

    def publish_build_update(self, build_id: str, status: str, **kwargs) -> None:
        from app.tasks.shared.events import publish_ingestion_build_update

        publish_ingestion_build_update(
            self.scenario_id,
            build_id,
            status,
            pipeline_type="training",
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "training",
            "scenario_id": self.scenario_id,
            "correlation_id": self.correlation_id,
            "raw_repo_id": self._raw_repo_id,
            "github_repo_id": self._github_repo_id,
            "full_name": self._full_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingPipelineContext":
        return cls(
            scenario_id=data["scenario_id"],
            correlation_id=data.get("correlation_id", ""),
            _raw_repo_id=data.get("raw_repo_id"),
            _github_repo_id=data.get("github_repo_id"),
            _full_name=data.get("full_name"),
        )


def deserialize_context(
    data: Dict[str, Any],
) -> "ModelPipelineContext | TrainingPipelineContext":
    """
    Deserialize a context dict back to the appropriate context class.

    Args:
        data: Dict with 'type' key indicating pipeline type

    Returns:
        ModelPipelineContext or TrainingPipelineContext instance

    Raises:
        ValueError: If unknown pipeline type
    """
    pipeline_type = data.get("type")

    if pipeline_type == "model":
        return ModelPipelineContext.from_dict(data)
    elif pipeline_type == "training":
        return TrainingPipelineContext.from_dict(data)
    else:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}")
