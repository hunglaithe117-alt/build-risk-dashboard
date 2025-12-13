"""Database entity models - represents the actual structure stored in MongoDB"""

from .base import BaseEntity, PyObjectId
from .base_repository import (
    BaseRepositoryEntity,
    Provider,
    TestFramework,
    ImportStatus,
    SyncStatus,
    EnrichmentImportStatus,
    RepoValidationStatus,
)

# Model flow entities (Bayesian model training)
from .model_repository import ModelRepository
from .model_build import ModelBuild, ModelBuildConclusion

# Enrichment flow entities (Dataset enrichment)
from .enrichment_repository import EnrichmentRepository
from .enrichment_build import EnrichmentBuild
from .dataset_build import DatasetBuild, DatasetBuildStatus
from .base_build import BaseBuildSample, ExtractionStatus

# Other entities
from .github_installation import GithubInstallation
from .oauth_identity import OAuthIdentity
from .user import User
from .dataset_template import DatasetTemplate
from .dataset import (
    DatasetProject,
    DatasetMapping,
    DatasetStats,
    ValidationStats,
    DatasetValidationStatus,
)
from .pipeline_run import (
    PipelineRun,
    NodeExecutionResult,
    PipelineRunStatus,
    NodeExecutionStatus,
)
from .export_job import ExportJob, ExportStatus, ExportFormat
from .workflow_run import WorkflowRunRaw

# CI Provider
from app.ci_providers.models import CIProvider

__all__ = [
    "BaseEntity",
    "BaseRepositoryEntity",
    "PyObjectId",
    # Model flow
    "ModelRepository",
    "ModelBuild",
    "ModelBuildConclusion",
    "ExtractionStatus",
    # Enrichment flow
    "EnrichmentRepository",
    "EnrichmentBuild",
    "ExtractionStatus",
    "RepoValidationStatus",
    "EnrichmentImportStatus",
    "DatasetBuild",
    "DatasetBuildStatus",
    # Other
    "GithubInstallation",
    "OAuthIdentity",
    "User",
    "DatasetProject",
    "DatasetMapping",
    "DatasetStats",
    "ValidationStats",
    "DatasetValidationStatus",
    "DatasetTemplate",
    "PipelineRun",
    "NodeExecutionResult",
    "PipelineRunStatus",
    "NodeExecutionStatus",
    "ExportJob",
    "ExportStatus",
    "ExportFormat",
    "WorkflowRunRaw",
    # Enums
    "Provider",
    "TestFramework",
    "CIProvider",
    "ImportStatus",
    "SyncStatus",
]
