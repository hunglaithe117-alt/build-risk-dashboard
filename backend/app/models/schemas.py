"""
Pydantic schemas for request/response validation
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# Build schemas
class BuildFeatureSnapshot(BaseModel):
    tr_build_id: Optional[int] = None
    gh_project_name: Optional[str] = None
    gh_is_pr: Optional[bool] = None
    gh_pr_created_at: Optional[datetime] = None
    gh_pull_req_num: Optional[int] = None
    gh_lang: Optional[str] = None
    git_branch: Optional[str] = None
    git_prev_commit_resolution_status: Optional[str] = None
    git_prev_built_commit: Optional[str] = None
    tr_prev_build: Optional[int] = None
    gh_team_size: Optional[int] = None
    git_all_built_commits: List[Dict[str, Any]] = Field(default_factory=list)
    git_num_all_built_commits: Optional[int] = None
    git_trigger_commit: Optional[str] = None
    tr_original_commit: Optional[str] = None
    gh_num_issue_comments: Optional[int] = None
    gh_num_commit_comments: Optional[int] = None
    gh_num_pr_comments: Optional[int] = None
    git_diff_src_churn: Optional[int] = None
    git_diff_test_churn: Optional[int] = None
    gh_diff_files_added: Optional[int] = None
    gh_diff_files_deleted: Optional[int] = None
    gh_diff_files_modified: Optional[int] = None
    gh_diff_tests_added: Optional[int] = None
    gh_diff_tests_deleted: Optional[int] = None
    gh_diff_src_files: Optional[int] = None
    gh_diff_doc_files: Optional[int] = None
    gh_diff_other_files: Optional[int] = None
    gh_num_commits_on_files_touched: Optional[int] = None
    gh_sloc: Optional[int] = None
    gh_test_lines: Optional[int] = None
    gh_test_cases: Optional[int] = None
    gh_asserts: Optional[int] = None
    gh_by_core_team_member: Optional[bool] = None
    gh_description_complexity: Optional[int] = None
    gh_build_started_at: Optional[datetime] = None
    gh_repo_age: Optional[int] = None
    gh_repo_num_commits: Optional[int] = None
    tr_job_id: Optional[str] = None
    tr_job_ids: List[str] = Field(default_factory=list)
    tr_log_lang: Optional[str] = None
    tr_log_lan_all: List[str] = Field(default_factory=list)
    tr_log_frameworks_all: List[str] = Field(default_factory=list)
    tr_log_num_jobs: Optional[int] = None
    tr_log_tests_run_sum: Optional[int] = None
    tr_log_tests_failed_sum: Optional[int] = None
    tr_log_tests_skipped_sum: Optional[int] = None
    tr_log_tests_ok_sum: Optional[int] = None
    tr_log_tests_fail_rate: Optional[float] = None
    tr_log_buildduration_sum: Optional[float] = None
    tr_log_buildduration_mean: Optional[float] = None
    tr_log_testduration_sum: Optional[float] = None
    tr_log_testduration_mean: Optional[float] = None
    tr_status: Optional[str] = None
    tr_duration: Optional[int] = None


class BuildBase(BaseModel):
    repository: str
    branch: str
    commit_sha: str
    build_number: str
    workflow_name: Optional[str] = None
    status: str
    conclusion: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    url: Optional[str] = None
    logs_url: Optional[str] = None
    features: Optional[BuildFeatureSnapshot] = None


class BuildCreate(BuildBase):
    """Schema for creating a new build"""

    pass


class BuildResponse(BuildBase):
    """Schema for build response"""

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BuildListItem(BuildResponse):
    """Build item with related analytics"""


class BuildListResponse(BaseModel):
    """Schema for paginated build list response"""

    total: int
    skip: int
    limit: int
    builds: List[BuildListItem]


# Risk assessment schemas removed (model inference disabled)


# Build detail with all related data
class BuildDetailResponse(BuildListItem):
    """Schema for detailed build information including all assessments"""


# Dashboard schemas
class DashboardMetrics(BaseModel):
    total_builds: int
    success_rate: float
    average_duration_minutes: float


class DashboardTrendPoint(BaseModel):
    date: str
    builds: int
    failures: int


class RepoDistributionEntry(BaseModel):
    repository: str
    builds: int

    class Config:
        populate_by_name = True


class DashboardSummaryResponse(BaseModel):
    metrics: DashboardMetrics
    trends: List[DashboardTrendPoint]
    repo_distribution: List[RepoDistributionEntry]

    class Config:
        from_attributes = True


BuildListItem.model_rebuild()
BuildDetailResponse.model_rebuild()


# GitHub integration schemas
class GithubRepositoryStatus(BaseModel):
    name: str
    lastSync: Optional[datetime] = None
    buildCount: int
    status: str


class GithubIntegrationStatusResponse(BaseModel):
    connected: bool
    organization: Optional[str] = None
    connectedAt: Optional[datetime] = None
    scopes: List[str]
    repositories: List[GithubRepositoryStatus] = []
    lastSyncStatus: str
    lastSyncMessage: Optional[str] = None
    accountLogin: Optional[str] = None
    accountName: Optional[str] = None
    accountAvatarUrl: Optional[str] = None


class GithubAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class GithubOAuthInitRequest(BaseModel):
    redirect_path: Optional[str] = None


# Data pipeline schemas
class PipelineStage(BaseModel):
    key: str
    label: str
    status: Literal["pending", "running", "completed", "blocked"]
    percent_complete: int = Field(..., ge=0, le=100)
    duration_seconds: Optional[int] = None
    items_processed: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    issues: List[str] = Field(default_factory=list)


class PipelineStatusResponse(BaseModel):
    last_run: datetime
    next_run: datetime
    normalized_features: int
    pending_repositories: int
    anomalies_detected: int
    stages: List[PipelineStage]


class QueueHealthResponse(BaseModel):
    last_heartbeat: datetime
    repositories_scheduled: int
    pending_import_jobs: int
    running_import_jobs: int
    builds_waiting_enrichment: int
    completed_builds: int


# GitHub repository import schemas
class GithubImportRequest(BaseModel):
    repository: str
    branch: str = Field(..., description="Default branch to scan (e.g., main)")
    initiated_by: Optional[str] = Field(
        default="admin", description="User requesting the import"
    )
    user_id: Optional[int] = Field(
        default=None, description="Owner user id (defaults to admin)"
    )


class GithubImportJobResponse(BaseModel):
    id: str
    repository: str
    branch: str
    user_id: int
    installation_id: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed"]
    progress: int = Field(..., ge=0, le=100)
    builds_imported: int
    commits_analyzed: int
    tests_collected: int
    initiated_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class RepoImportRequest(BaseModel):
    full_name: str = Field(..., description="Repository full name (e.g., owner/name)")
    provider: str = Field(default="github")
    user_id: Optional[int] = Field(
        default=None, description="Owner user id (defaults to admin)"
    )
    installation_id: Optional[str] = Field(
        default=None,
        description="GitHub App installation id (required for private repos, optional for public repos)",
    )


class RepoResponse(BaseModel):
    id: str
    user_id: int
    provider: str
    full_name: str
    default_branch: Optional[str] = None
    is_private: bool = False
    main_lang: Optional[str] = None
    github_repo_id: Optional[int] = None
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    installation_id: Optional[str] = None

    class Config:
        from_attributes = True


class RepoScanRequest(BaseModel):
    mode: Literal["latest", "full"] = "latest"
    initiated_by: Optional[str] = Field(default="admin", description="Requested by")


class RepoScanJobResponse(BaseModel):
    id: str
    repo_id: int
    mode: Literal["latest", "full"]
    status: Literal["pending", "running", "completed", "failed"]
    progress: int = Field(..., ge=0, le=100)
    initiated_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    last_error: Optional[str] = None


# Settings & admin schemas
class SystemSettings(BaseModel):
    auto_rescan_enabled: bool = False
    updated_at: datetime
    updated_by: str


class SystemSettingsUpdate(BaseModel):
    auto_rescan_enabled: Optional[bool] = None
    updated_by: Optional[str] = None
    auto_rescan_enabled: Optional[bool] = None
    updated_by: Optional[str] = None


class ActivityLogEntry(BaseModel):
    id: str = Field(..., alias="_id")
    action: str
    actor: str
    scope: str
    message: str
    created_at: datetime
    metadata: Dict[str, str] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class ActivityLogListResponse(BaseModel):
    logs: List[ActivityLogEntry]


class NotificationPolicy(BaseModel):
    channels: List[str]
    muted_repositories: List[str] = []
    last_updated_at: datetime
    last_updated_by: str


class NotificationPolicyUpdate(BaseModel):
    channels: Optional[List[str]] = None
    muted_repositories: Optional[List[str]] = None
    updated_by: str


class NotificationItem(BaseModel):
    id: str = Field(..., alias="_id")
    build_id: int
    repository: str
    branch: str
    status: Literal["new", "sent", "acknowledged"]
    created_at: datetime
    message: str

    class Config:
        populate_by_name = True


class NotificationListResponse(BaseModel):
    notifications: List[NotificationItem]


class UserRoleDefinition(BaseModel):
    role: str
    description: str
    permissions: List[str]
    admin_only: bool = False


class RoleListResponse(BaseModel):
    roles: List[UserRoleDefinition]


# GitHub App Installation schemas
class GithubInstallationResponse(BaseModel):
    id: str = Field(..., alias="_id")
    installation_id: str
    account_login: Optional[str] = None
    account_type: Optional[str] = None  # "User" or "Organization"
    installed_at: datetime
    revoked_at: Optional[datetime] = None
    uninstalled_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        populate_by_name = True


class GithubInstallationListResponse(BaseModel):
    installations: List[GithubInstallationResponse]


class UserResponse(BaseModel):
    id: int = Field(..., alias="_id")
    email: str
    name: Optional[str] = None
    role: Literal["admin", "user"] = "user"
    created_at: datetime

    class Config:
        populate_by_name = True


class OAuthIdentityResponse(BaseModel):
    id: int = Field(..., alias="_id")
    user_id: int
    provider: str
    external_user_id: str
    scopes: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        populate_by_name = True


class GithubLoginRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    scope: Optional[str] = None


class UserLoginResponse(BaseModel):
    user: UserResponse
    identity: OAuthIdentityResponse
