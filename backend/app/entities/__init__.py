# CI Provider
from app.ci_providers.models import CIProvider

from .base import BaseEntity, PyObjectId
from .data_quality import (
    DataQualityMetric,
    DataQualityReport,
    QualityEvaluationStatus,
    QualityIssue,
    QualityIssueSeverity,
)

# Dataset entities
from .dataset import (
    DatasetMapping,
    DatasetProject,
    DatasetStats,
    DatasetValidationStatus,
    ValidationStats,
)
from .dataset_build import DatasetBuild, DatasetBuildStatus

# Dataset enrichment flow entities
from .dataset_enrichment_build import DatasetEnrichmentBuild
from .dataset_template import DatasetTemplate

# Shared enums
from .enums import (
    ExtractionStatus,
    TestFramework,
)
from .export_job import ExportFormat, ExportJob, ExportStatus
from .feature_audit_log import (
    AuditLogCategory,
    FeatureAuditLog,
    NodeExecutionResult,
    NodeExecutionStatus,
)

# Model training flow entities
from .model_import_build import ModelImportBuild, ModelImportBuildStatus
from .model_repo_config import ModelImportStatus, ModelRepoConfig
from .model_training_build import ModelTrainingBuild
from .notification import Notification, NotificationType

# Other entities
# from .github_installation import GithubInstallation
from .oauth_identity import OAuthIdentity
from .raw_build_run import RawBuildRun

# Raw data entities (shared across flows)
from .raw_repository import RawRepository
from .user import User

__all__ = [
    # Base
    "BaseEntity",
    "PyObjectId",
    # Enums
    "TestFramework",
    "ExtractionStatus",
    "ModelImportStatus",
    "CIProvider",
    "RawRepository",
    "RawBuildRun",
    "ModelRepoConfig",
    "ModelImportBuild",
    "ModelImportBuildStatus",
    "ModelTrainingBuild",
    "DatasetEnrichmentBuild",
    "DatasetProject",
    "DatasetMapping",
    "DatasetStats",
    "ValidationStats",
    "DatasetValidationStatus",
    "DatasetBuild",
    "DatasetBuildStatus",
    "OAuthIdentity",
    "User",
    "DatasetTemplate",
    "FeatureAuditLog",
    "FeatureAuditLogStatus",
    "AuditLogCategory",
    "NodeExecutionResult",
    "NodeExecutionStatus",
    "ExportJob",
    "ExportStatus",
    "ExportFormat",
    "Notification",
    "NotificationType",
    "DataQualityReport",
    "DataQualityMetric",
    "QualityEvaluationStatus",
    "QualityIssue",
    "QualityIssueSeverity",
]
