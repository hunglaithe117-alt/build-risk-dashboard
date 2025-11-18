"""Build entity - represents a CI/CD build in the database"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class BuildFeatures(BaseModel):
    """Feature snapshot for ML/analytics"""

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


class Build(BaseModel):
    """Build entity stored in MongoDB"""

    id: Optional[ObjectId] = Field(None, alias="_id")
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
    features: Optional[BuildFeatures] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
