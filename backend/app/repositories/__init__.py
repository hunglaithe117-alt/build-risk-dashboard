"""Repository layer for database operations"""

from .base import BaseRepository
from .data_quality_repository import DataQualityRepository

# === NEW REPOSITORIES (Architecture Merge) ===
# Build Source repositories
from .build_source import BuildSourceRepository
from .source_build import SourceBuildRepository
from .source_repo_stats import SourceRepoStatsRepository

# Training Pipeline repositories
from .training_scenario import TrainingScenarioRepository
from .training_ingestion_build import TrainingIngestionBuildRepository
from .training_enrichment_build import TrainingEnrichmentBuildRepository
from .training_dataset_split import TrainingDatasetSplitRepository

# Dataset template (kept for upload presets)
from .dataset_template_repository import DatasetTemplateRepository
from .feature_audit_log import FeatureAuditLogRepository

# Model training flow repositories
from .model_repo_config import ModelRepoConfigRepository
from .model_training_build import ModelTrainingBuildRepository
from .notification import NotificationRepository

# Other repositories
from .oauth_identity import OAuthIdentityRepository
from .raw_build_run import RawBuildRunRepository

# Raw data repositories (shared across flows)
from .raw_repository import RawRepositoryRepository
from .user import UserRepository

__all__ = [
    "BaseRepository",
    # === NEW REPOSITORIES ===
    # Build Source
    "BuildSourceRepository",
    "SourceBuildRepository",
    "SourceRepoStatsRepository",
    # Training Pipeline
    "TrainingScenarioRepository",
    "TrainingIngestionBuildRepository",
    "TrainingEnrichmentBuildRepository",
    "TrainingDatasetSplitRepository",
    # Raw data (shared)
    "RawRepositoryRepository",
    "RawBuildRunRepository",
    # Model training flow
    "ModelRepoConfigRepository",
    "ModelTrainingBuildRepository",
    # Other
    "OAuthIdentityRepository",
    "UserRepository",
    "DatasetTemplateRepository",
    "FeatureAuditLogRepository",
    "NotificationRepository",
    # Data Quality
    "DataQualityRepository",
]
