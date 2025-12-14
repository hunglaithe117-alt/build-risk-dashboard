"""Repository layer for database operations"""

from .base import BaseRepository

# Raw data repositories (shared across flows)
from .raw_repository import RawRepositoryRepository
from .raw_build_run import RawBuildRunRepository

# Model training flow repositories
from .model_repo_config import ModelRepoConfigRepository
from .model_training_build import ModelTrainingBuildRepository

# Dataset enrichment flow repositories
from .dataset_repo_config import DatasetRepoConfigRepository
from .dataset_enrichment_build import DatasetEnrichmentBuildRepository

# Dataset repositories
from .dataset_repository import DatasetRepository
from .dataset_build_repository import DatasetBuildRepository

# Other repositories
from .github_installation import GithubInstallationRepository
from .oauth_identity import OAuthIdentityRepository
from .user import UserRepository
from .dataset_template_repository import DatasetTemplateRepository
from .pipeline_run import PipelineRunRepository

__all__ = [
    "BaseRepository",
    # Raw data (shared)
    "RawRepositoryRepository",
    "RawBuildRunRepository",
    # Model training flow
    "ModelRepoConfigRepository",
    "ModelTrainingBuildRepository",
    # Dataset enrichment flow
    "DatasetRepoConfigRepository",
    "DatasetEnrichmentBuildRepository",
    # Dataset
    "DatasetRepository",
    "DatasetBuildRepository",
    # Other
    "GithubInstallationRepository",
    "OAuthIdentityRepository",
    "UserRepository",
    "DatasetTemplateRepository",
    "PipelineRunRepository",
]
