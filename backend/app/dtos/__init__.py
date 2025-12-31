"""Data Transfer Objects (DTOs) for API requests and responses"""

from .admin_user import (
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
from .auth import (
    AuthVerifyResponse,
    GithubLoginRequest,
    UserLoginResponse,
)
from .build import (
    BuildDetail,
    BuildListResponse,
    BuildSummary,
    ImportBuildListResponse,
    ImportBuildSummary,
    ResourceStatusDTO,
    TrainingBuildListResponse,
    TrainingBuildSummary,
)
from .dashboard import (
    DashboardMetrics,
    DashboardSummaryResponse,
    DashboardTrendPoint,
    RepoDistributionEntry,
)
from .dataset import (
    BuildValidationFiltersDto,
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
    RepoValidationItem,
    RepoValidationResponse,
)
from .dataset_repo import (
    DatasetRepoListResponse,
    DatasetRepoSummary,
)
from .dataset_template import (
    DatasetTemplateListResponse,
    DatasetTemplateResponse,
)
from .dataset_version import (
    CreateVersionRequest,
    VersionListResponse,
    VersionResponse,
)
from .feature import (
    DAGEdgeResponse,
    DAGNodeResponse,
    DAGResponse,
    ExecutionLevelResponse,
    FeatureDefinitionResponse,
    FeatureListResponse,
    FeatureSummaryResponse,
    ValidationResponse,
)
from .github import (
    GithubAuthorizeResponse,
    # GithubInstallationListResponse,
    # GithubInstallationResponse,
    GithubOAuthInitRequest,
    GithubRepositoryStatus,
)
from .integration import (
    SonarWebhookPayload,
    ToolInfoResponse,
    ToolsListResponse,
)
from .notification import (
    CreateNotificationRequest,
    MarkReadResponse,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from .repository import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSearchResponse,
    RepoSuggestion,
    RepoSuggestionListResponse,
)
from .settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
    CircleCISettingsDto,
    NotificationSettingsDto,
    SonarQubeSettingsDto,
    TravisCISettingsDto,
    TrivySettingsDto,
)
from .token import (
    TokenCreateRequest,
    TokenListResponse,
    TokenPoolStatusResponse,
    TokenResponse,
    TokenUpdateRequest,
    TokenVerifyResponse,
)
from .user import (
    OAuthIdentityResponse,
    UserResponse,
    UserUpdate,
)
from .user_settings import (
    UpdateUserSettingsRequest,
    UserSettingsResponse,
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
    # "GithubInstallationListResponse",
    # "GithubInstallationResponse",
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
    # User
    "OAuthIdentityResponse",
    "UserResponse",
    "UserUpdate",
    # Build
    "BuildSummary",
    "BuildDetail",
    "BuildListResponse",
    # Import Builds (Ingestion)
    "ImportBuildSummary",
    "ImportBuildListResponse",
    "ResourceStatusDTO",
    # Training Builds (Processing)
    "TrainingBuildSummary",
    "TrainingBuildListResponse",
    # Dataset
    "DatasetResponse",
    "DatasetListResponse",
    "DatasetCreateRequest",
    "BuildValidationFiltersDto",
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
    "AdminUserUpdateRequest",
    # Notification
    "NotificationResponse",
    "NotificationListResponse",
    "UnreadCountResponse",
    "MarkReadResponse",
    "CreateNotificationRequest",
    # User Settings
    "UserSettingsResponse",
    "UpdateUserSettingsRequest",
    # Integration / Scan
    "ToolInfoResponse",
    "ToolsListResponse",
    "SonarWebhookPayload",
]
