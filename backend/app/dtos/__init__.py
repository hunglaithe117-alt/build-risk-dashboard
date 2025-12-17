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
    RepoValidationItem,
    RepoValidationResponse,
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
from .dataset_version import (
    CreateVersionRequest,
    VersionResponse,
    VersionListResponse,
)
from .dataset_repo import (
    DatasetRepoSummary,
    DatasetRepoListResponse,
)
from .settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
    CircleCISettingsDto,
    TravisCISettingsDto,
    SonarQubeSettingsDto,
    TrivySettingsDto,
    NotificationSettingsDto,
)
from .admin_user import (
    AdminUserResponse,
    AdminUserListResponse,
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AdminUserRoleUpdateRequest,
)
from .admin_repo import (
    RepoAccessSummary,
    AdminRepoListResponse,
    RepoAccessResponse,
    GrantAccessRequest,
    RevokeAccessRequest,
    VisibilityUpdateRequest,
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
    "RepoValidationItem",
    "RepoValidationResponse",
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
    # Dataset Version
    "CreateVersionRequest",
    "VersionResponse",
    "VersionListResponse",
    # Dataset Repo
    "DatasetRepoSummary",
    "DatasetRepoListResponse",
    # Settings
    "ApplicationSettingsResponse",
    "ApplicationSettingsUpdateRequest",
    "CircleCISettingsDto",
    "TravisCISettingsDto",
    "SonarQubeSettingsDto",
    "TrivySettingsDto",
    "NotificationSettingsDto",
    # Admin User
    "AdminUserResponse",
    "AdminUserListResponse",
    "AdminUserCreateRequest",
    "AdminUserUpdateRequest",
    "AdminUserRoleUpdateRequest",
    # Admin Repo
    "RepoAccessSummary",
    "AdminRepoListResponse",
    "RepoAccessResponse",
    "GrantAccessRequest",
    "RevokeAccessRequest",
    "VisibilityUpdateRequest",
]
