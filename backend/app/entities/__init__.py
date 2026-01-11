# CI Provider
from app.ci_providers.models import CIProvider

from .base import BaseEntity, PyObjectId

# === NEW ENTITIES (Architecture Merge) ===
# Build Source (data collection layer)
from .build_source import (
    BuildSource,
    SourceMapping,
    ValidationStats,
    ValidationStatus,
)
from .data_quality import (
    DataQualityMetric,
    DataQualityReport,
    QualityEvaluationStatus,
    QualityIssue,
    QualityIssueSeverity,
)

# Dataset template (kept for upload presets)
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
from .oauth_identity import OAuthIdentity
from .raw_build_run import RawBuildRun

# Raw data entities (shared across flows)
from .raw_repository import RawRepository
from .source_build import SourceBuild, SourceBuildStatus
from .source_repo_stats import SourceRepoStats
from .training_dataset_split import TrainingDatasetSplit
from .training_enrichment_build import TrainingEnrichmentBuild
from .training_ingestion_build import (
    IngestionStatus,
    ResourceStatus,
    ResourceStatusEntry,
    TrainingIngestionBuild,
)

# Training Pipeline (training layer)
from .training_scenario import (
    DataSourceConfig,
    FeatureConfig,
    GroupByDimension,
    OutputConfig,
    PreprocessingConfig,
    ScenarioStatus,
    SplitStrategy,
    SplittingConfig,
    TrainingScenario,
)
from .user import User

__all__ = [
    # Base
    "BaseEntity",
    "PyObjectId",
    # === NEW ENTITIES ===
    # Build Source
    "BuildSource",
    "SourceMapping",
    "ValidationStats",
    "ValidationStatus",
    "SourceBuild",
    "SourceBuildStatus",
    "SourceRepoStats",
    # Training Scenario
    "TrainingScenario",
    "ScenarioStatus",
    "DataSourceConfig",
    "FeatureConfig",
    "SplittingConfig",
    "PreprocessingConfig",
    "OutputConfig",
    "SplitStrategy",
    "GroupByDimension",
    # Ingestion & Enrichment
    "TrainingIngestionBuild",
    "IngestionStatus",
    "ResourceStatus",
    "ResourceStatusEntry",
    "TrainingEnrichmentBuild",
    "TrainingDatasetSplit",
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
    # Other
    "OAuthIdentity",
    "User",
    "DatasetTemplate",
    "FeatureAuditLog",
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
