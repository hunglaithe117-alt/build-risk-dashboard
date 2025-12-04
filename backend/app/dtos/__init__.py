"""Data Transfer Objects (DTOs) for API requests and responses"""

from .auth import (
    AuthVerifyResponse,
    GithubLoginRequest,
    UserLoginResponse,
)
from .dashboard import (
    DashboardMetrics,
    DashboardSummaryResponse,
    DashboardTrendPoint,
    RepoDistributionEntry,
)
from .build import (
    BuildDetail,
    BuildListResponse,
    BuildSummary,
)
from .github import (
    GithubAuthorizeResponse,
    GithubInstallationListResponse,
    GithubInstallationResponse,
    GithubOAuthInitRequest,
    GithubRepositoryStatus,
)
from .repository import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSearchResponse,
    RepoSuggestion,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
)
from .user import (
    OAuthIdentityResponse,
    UserResponse,
)
from .dataset import (
    AvailableFeaturesResponse,
    DatasetJobCreateRequest,
    DatasetJobCreatedResponse,
    DatasetJobListResponse,
    DatasetJobResponse,
    DownloadUrlResponse,
    FeatureCategoryResponse,
    FeatureDefinitionResponse,
    ResolvedDependenciesResponse,
)

__all__ = [
    # Auth
    "AuthVerifyResponse",
    "GithubLoginRequest",
    "UserLoginResponse",
    # Dashboard
    "DashboardMetrics",
    "DashboardSummaryResponse",
    "DashboardTrendPoint",
    "RepoDistributionEntry",
    # GitHub
    "GithubAuthorizeResponse",
    "GithubInstallationListResponse",
    "GithubInstallationResponse",
    "GithubOAuthInitRequest",
    "GithubRepositoryStatus",
    # Repository
    "RepoDetailResponse",
    "RepoImportRequest",
    "RepoListResponse",
    "RepoResponse",
    "RepoSearchResponse",
    "RepoSuggestion",
    "RepoSuggestionListResponse",
    "RepoUpdateRequest",
    # User
    "OAuthIdentityResponse",
    "UserResponse",
    # Build
    "BuildSummary",
    "BuildDetail",
    "BuildListResponse",
    # Dataset
    "AvailableFeaturesResponse",
    "DatasetJobCreateRequest",
    "DatasetJobCreatedResponse",
    "DatasetJobListResponse",
    "DatasetJobResponse",
    "DownloadUrlResponse",
    "FeatureCategoryResponse",
    "FeatureDefinitionResponse",
    "ResolvedDependenciesResponse",
]
