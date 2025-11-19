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
from .github import (
    GithubAuthorizeResponse,
    GithubInstallationListResponse,
    GithubInstallationResponse,
    GithubOAuthInitRequest,
    GithubRepositoryStatus,
)
from .pipeline import (
    PipelineStage,
    PipelineStatusResponse,
    QueueHealthResponse,
)
from .repository import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoResponse,
    RepoSuggestion,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
)
from .user import (
    OAuthIdentityResponse,
    UserResponse,
    UserRoleDefinition,
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
    # Pipeline
    "PipelineStage",
    "PipelineStatusResponse",
    "QueueHealthResponse",
    # Repository
    "RepoDetailResponse",
    "RepoImportRequest",
    "RepoResponse",
    "RepoSuggestion",
    "RepoSuggestionListResponse",
    "RepoUpdateRequest",
    # User
    "OAuthIdentityResponse",
    "UserResponse",
    "UserRoleDefinition",
]
