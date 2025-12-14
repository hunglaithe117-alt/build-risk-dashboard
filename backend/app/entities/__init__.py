"""Database entity models - represents the actual structure stored in MongoDB"""

from .base import BaseEntity, PyObjectId

# Shared enums
from .enums import (
    TestFramework,
    ExtractionStatus,
    ModelImportStatus,
    ModelSyncStatus,
    DatasetRepoValidationStatus,
)

# Raw data entities (shared across flows)
from .raw_repository import RawRepository
from .raw_build_run import RawBuildRun

# Model training flow entities
from .model_repo_config import ModelRepoConfig
from .model_training_build import ModelTrainingBuild

# Dataset enrichment flow entities
from .dataset_repo_config import DatasetRepoConfig
from .dataset_enrichment_build import DatasetEnrichmentBuild

# Dataset entities
from .dataset import (
    DatasetProject,
    DatasetMapping,
    DatasetStats,
    ValidationStats,
    DatasetValidationStatus,
)
from .dataset_build import DatasetBuild, DatasetBuildStatus

# Other entities
from .github_installation import GithubInstallation
from .oauth_identity import OAuthIdentity
from .user import User
from .dataset_template import DatasetTemplate
from .pipeline_run import (
    PipelineRun,
    NodeExecutionResult,
    PipelineRunStatus,
    NodeExecutionStatus,
)
from .export_job import ExportJob, ExportStatus, ExportFormat

# CI Provider
from app.ci_providers.models import CIProvider

__all__ = [
    # Base
    "BaseEntity",
    "PyObjectId",
    # Enums
    "TestFramework",
    "ExtractionStatus",
    "ModelImportStatus",
    "ModelSyncStatus",
    "DatasetRepoValidationStatus",
    "CIProvider",
    # Raw data (shared)
    "RawRepository",
    "RawBuildRun",
    # Model training flow
    "ModelRepoConfig",
    "ModelTrainingBuild",
    # Dataset enrichment flow
    "DatasetRepoConfig",
    "DatasetEnrichmentBuild",
    # Dataset
    "DatasetProject",
    "DatasetMapping",
    "DatasetStats",
    "ValidationStats",
    "DatasetValidationStatus",
    "DatasetBuild",
    "DatasetBuildStatus",
    # Other
    "GithubInstallation",
    "OAuthIdentity",
    "User",
    "DatasetTemplate",
    "PipelineRun",
    "NodeExecutionResult",
    "PipelineRunStatus",
    "NodeExecutionStatus",
    "ExportJob",
    "ExportStatus",
    "ExportFormat",
]
