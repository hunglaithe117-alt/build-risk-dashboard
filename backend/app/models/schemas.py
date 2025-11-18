"""
Pydantic schemas for request/response validation
"""

from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# Custom validator for MongoDB ObjectId
def validate_object_id(v: Any) -> str:
    """Validate and convert ObjectId to string."""
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


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

    id: PyObjectId = Field(..., alias="_id")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)


class BuildListItem(BuildResponse):
    """Build item with related analytics"""


class BuildListResponse(BaseModel):
    """Schema for paginated build list response"""

    total: int
    skip: int
    limit: int
    builds: List[BuildListItem]


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


class DashboardSummaryResponse(BaseModel):
    metrics: DashboardMetrics
    trends: List[DashboardTrendPoint]
    repo_distribution: List[RepoDistributionEntry]


BuildListItem.model_rebuild()
BuildDetailResponse.model_rebuild()


# GitHub integration schemas
class GithubRepositoryStatus(BaseModel):
    name: str
    lastSync: Optional[datetime] = None
    buildCount: int
    status: str


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
    user_id: Optional[str] = Field(
        default=None, description="Owner user id (defaults to admin)"
    )


class GithubImportJobResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    repository: str
    branch: str
    user_id: Optional[PyObjectId] = None
    installation_id: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed", "waiting_webhook"]
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

    model_config = ConfigDict(populate_by_name=True)


class RepoImportRequest(BaseModel):
    full_name: str = Field(..., description="Repository full name (e.g., owner/name)")
    provider: str = Field(default="github")
    user_id: Optional[str] = Field(
        default=None, description="Owner user id (defaults to admin)"
    )
    installation_id: Optional[str] = Field(
        default=None,
        description="GitHub App installation id (required for private repos, optional for public repos)",
    )


class RepoResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    user_id: Optional[PyObjectId] = None
    provider: str
    full_name: str
    default_branch: Optional[str] = None
    is_private: bool = False
    main_lang: Optional[str] = None
    github_repo_id: Optional[int] = None
    created_at: datetime
    last_scanned_at: Optional[datetime] = None
    installation_id: Optional[str] = None
    ci_provider: Literal["github_actions", "travis_ci"] = "github_actions"
    monitoring_enabled: bool = True
    sync_status: Literal["healthy", "error", "disabled"] = "healthy"
    webhook_status: Literal["active", "inactive"] = "inactive"
    ci_token_status: Literal["valid", "missing"] = "valid"
    tracked_branches: List[str] = Field(default_factory=list)
    total_builds_imported: int = 0
    last_sync_error: Optional[str] = None
    notes: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class RepoDetailResponse(RepoResponse):
    metadata: Optional[Dict[str, Any]] = None


class RepoUpdateRequest(BaseModel):
    ci_provider: Optional[str] = None
    monitoring_enabled: Optional[bool] = None
    sync_status: Optional[Literal["healthy", "error", "disabled"]] = None
    tracked_branches: Optional[List[str]] = None
    webhook_status: Optional[Literal["active", "inactive"]] = None
    ci_token_status: Optional[Literal["valid", "missing"]] = None
    default_branch: Optional[str] = None
    notes: Optional[str] = None


class RepoSuggestion(BaseModel):
    full_name: str
    description: Optional[str] = None
    default_branch: Optional[str] = None
    private: bool = False
    owner: Optional[str] = None
    installed: bool = False
    requires_installation: bool = False
    source: Literal["owned", "search"] = "owned"


class RepoSuggestionListResponse(BaseModel):
    items: List[RepoSuggestion]


class RepoScanRequest(BaseModel):
    mode: Literal["latest", "full"] = "latest"
    initiated_by: Optional[str] = Field(default="admin", description="Requested by")


class RepoScanJobResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    repo_id: PyObjectId
    mode: Literal["latest", "full"]
    status: Literal["pending", "running", "completed", "failed"]
    progress: int = Field(..., ge=0, le=100)
    initiated_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    last_error: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class UserRoleDefinition(BaseModel):
    role: str
    description: str
    permissions: List[str]
    admin_only: bool = False


# GitHub App Installation schemas
class GithubInstallationResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    installation_id: str
    account_login: Optional[str] = None
    account_type: Optional[str] = None  # "User" or "Organization"
    installed_at: datetime
    revoked_at: Optional[datetime] = None
    uninstalled_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class GithubInstallationListResponse(BaseModel):
    installations: List[GithubInstallationResponse]


class UserResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    email: str
    name: Optional[str] = None
    role: Literal["admin", "user"] = "user"
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class OAuthIdentityResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    user_id: PyObjectId
    provider: str
    external_user_id: str
    scopes: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class GithubLoginRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    scope: Optional[str] = None


class UserLoginResponse(BaseModel):
    user: UserResponse
    identity: OAuthIdentityResponse


class AuthVerifyResponse(BaseModel):
    authenticated: bool
    reason: Optional[str] = None
    user: Optional[Dict[str, Optional[str]]] = None
    github: Optional[Dict[str, Optional[str]]] = None
