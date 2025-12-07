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
    DatasetResponse,
    DatasetListResponse,
    DatasetCreateRequest,
    DatasetUpdateRequest,
)
from .dataset_template import (
    DatasetTemplateResponse,
    DatasetTemplateListResponse,
)
from .token import (
    TokenCreateRequest,
    TokenUpdateRequest,
    TokenResponse,
    TokenPoolStatusResponse,
    TokenVerifyResponse,
    TokenListResponse,
)
from .feature import (
    FeatureDefinitionResponse,
    FeatureListResponse,
    FeatureSummaryResponse,
    ValidationResponse,
    DAGNodeResponse,
    DAGEdgeResponse,
    ExecutionLevelResponse,
    DAGResponse,
)
from .enrichment import (
    EnrichmentValidateRequest,
    EnrichmentStartRequest,
    EnrichmentValidateResponse,
    EnrichmentJobResponse,
    EnrichmentStartResponse,
    EnrichmentStatusResponse,
    EnrichmentJobListResponse,
    EnrichmentProgressEvent,
    EnrichmentCompleteEvent,
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
    "DatasetResponse",
    "DatasetListResponse",
    "DatasetCreateRequest",
    "DatasetUpdateRequest",
    # Dataset templates
    "DatasetTemplateResponse",
    "DatasetTemplateListResponse",
    # Token
    "TokenCreateRequest",
    "TokenUpdateRequest",
    "TokenResponse",
    "TokenPoolStatusResponse",
    "TokenVerifyResponse",
    "TokenListResponse",
    # Feature
    "FeatureDefinitionResponse",
    "FeatureListResponse",
    "FeatureSummaryResponse",
    "ValidationResponse",
    "DAGNodeResponse",
    "DAGEdgeResponse",
    "ExecutionLevelResponse",
    "DAGResponse",
    # Enrichment
    "EnrichmentValidateRequest",
    "EnrichmentStartRequest",
    "EnrichmentValidateResponse",
    "EnrichmentJobResponse",
    "EnrichmentStartResponse",
    "EnrichmentStatusResponse",
    "EnrichmentJobListResponse",
    "EnrichmentProgressEvent",
    "EnrichmentCompleteEvent",
]

