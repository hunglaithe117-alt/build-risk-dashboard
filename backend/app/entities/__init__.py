"""Database entity models - represents the actual structure stored in MongoDB"""

from .base import BaseEntity, PyObjectId

# Model flow entities (Bayesian model training)
from .model_repository import (
    ModelRepository,
    Provider,
    TestFramework,
    ImportStatus,
)
from .model_build import ModelBuild, BuildStatus, ExtractionStatus

# Enrichment flow entities (Dataset enrichment)
from .enrichment_repository import (
    EnrichmentRepository,
    EnrichmentImportStatus,
    RepoValidationStatus,
)
from .enrichment_build import EnrichmentBuild, EnrichmentExtractionStatus
from .dataset_build import DatasetBuild, DatasetBuildStatus

# Other entities
from .github_installation import GithubInstallation
from .oauth_identity import OAuthIdentity
from .user import User
from .dataset_template import DatasetTemplate
from .dataset import DatasetProject, DatasetMapping, DatasetStats, ValidationStats
from .github_token import GithubToken
from .pipeline_run import PipelineRun, NodeExecutionResult
from .enrichment_job import EnrichmentJob
from .workflow_run import WorkflowRunRaw

# CI Provider
from app.ci_providers.models import CIProvider

__all__ = [
    "BaseEntity",
    "PyObjectId",
    # Model flow
    "ModelRepository",
    "ModelBuild",
    "BuildStatus",
    "ExtractionStatus",
    # Enrichment flow
    "EnrichmentRepository",
    "EnrichmentBuild",
    "EnrichmentImportStatus",
    "EnrichmentExtractionStatus",
    "RepoValidationStatus",
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
    "GithubToken",
    "DatasetTemplate",
    "PipelineRun",
    "NodeExecutionResult",
    "EnrichmentJob",
    "WorkflowRunRaw",
    # Enums
    "Provider",
    "TestFramework",
    "CIProvider",
    "ImportStatus",
]
