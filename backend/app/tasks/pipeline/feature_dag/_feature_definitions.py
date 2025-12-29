"""
Centralized Feature Definitions Registry.

This module provides a single source of truth for all feature metadata,
replacing inline @feature_metadata decorators and runtime type inference.

Usage:
    from app.tasks.pipeline.feature_dag._feature_definitions import (
        get_feature_definition,
        get_feature_data_type,
        FEATURE_REGISTRY,
    )

    # Get a single definition
    defn = get_feature_definition("git_all_built_commits")

    # Get data type for statistics service
    data_type = get_feature_data_type("gh_team_size")  # "integer"
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.tasks.pipeline.feature_dag._metadata import (
    FeatureCategory,
    FeatureDataType,
    OutputFormat,
)
from app.tasks.pipeline.shared.resources import FeatureResource


@dataclass
class FeatureDefinition:
    """Definition of a single feature's metadata."""

    name: str
    display_name: str
    description: str
    category: FeatureCategory
    data_type: FeatureDataType
    required_resources: List[FeatureResource] = field(default_factory=list)
    nullable: bool = True
    unit: Optional[str] = None
    output_format: Optional[OutputFormat] = None
    valid_range: Optional[Tuple[float, float]] = None
    valid_values: Optional[List[str]] = None
    example_value: Optional[str] = None


# FEATURE REGISTRY
# All features are defined here with their metadata.

FEATURE_REGISTRY: Dict[str, FeatureDefinition] = {
    # =========================================================================
    # BUILD FEATURES (build_features.py)
    # =========================================================================
    "tr_build_id": FeatureDefinition(
        name="tr_build_id",
        display_name="Build ID",
        description="Unique identifier for the workflow run",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "tr_build_number": FeatureDefinition(
        name="tr_build_number",
        display_name="Build Number",
        description="Sequential build number for this workflow",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "tr_original_commit": FeatureDefinition(
        name="tr_original_commit",
        display_name="Original Commit",
        description="Original commit SHA that triggered the build",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "tr_status": FeatureDefinition(
        name="tr_status",
        display_name="Build Status",
        description="Normalized build status (passed, failed, cancelled, errored)",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_RUN],
        valid_values=["passed", "failed", "cancelled", "errored", "unknown"],
    ),
    "tr_duration": FeatureDefinition(
        name="tr_duration",
        display_name="Build Duration",
        description="Build duration in seconds",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_RUN],
        unit="seconds",
    ),
    "tr_log_lan_all": FeatureDefinition(
        name="tr_log_lan_all",
        display_name="Source Languages",
        description="All source languages for the repository",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.LIST_STRING,
        required_resources=[FeatureResource.REPO],
        output_format=OutputFormat.COMMA_SEPARATED,
    ),
    "gh_project_name": FeatureDefinition(
        name="gh_project_name",
        display_name="Project Name",
        description="Full repository name (owner/repo)",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.REPO],
    ),
    "gh_lang": FeatureDefinition(
        name="gh_lang",
        display_name="Primary Language",
        description="Primary programming language of the repository",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.REPO],
    ),
    "ci_provider": FeatureDefinition(
        name="ci_provider",
        display_name="CI Provider",
        description="CI/CD provider name (github_actions, travis, circleci)",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "git_trigger_commit": FeatureDefinition(
        name="git_trigger_commit",
        display_name="Trigger Commit",
        description="Commit SHA that triggered the build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "gh_build_started_at": FeatureDefinition(
        name="gh_build_started_at",
        display_name="Build Started At",
        description="Build start timestamp in ISO format",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.DATETIME,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "git_branch": FeatureDefinition(
        name="git_branch",
        display_name="Branch",
        description="Branch name that triggered the build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "gh_is_pr": FeatureDefinition(
        name="gh_is_pr",
        display_name="Is PR Build",
        description="Whether this build is triggered by a pull request",
        category=FeatureCategory.PR_INFO,
        data_type=FeatureDataType.BOOLEAN,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
    "gh_pull_req_num": FeatureDefinition(
        name="gh_pull_req_num",
        display_name="PR Number",
        description="Pull request number (works with all CI providers)",
        category=FeatureCategory.PR_INFO,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_RUN],
        nullable=True,
    ),
    "gh_pr_created_at": FeatureDefinition(
        name="gh_pr_created_at",
        display_name="PR Created At",
        description="Pull request creation timestamp from GitHub API",
        category=FeatureCategory.PR_INFO,
        data_type=FeatureDataType.DATETIME,
        required_resources=[FeatureResource.GITHUB_API, FeatureResource.BUILD_RUN],
        nullable=True,
    ),
    # =========================================================================
    # GIT FEATURES (git_features.py)
    # =========================================================================
    # --- git_commit_info group ---
    "git_all_built_commits": FeatureDefinition(
        name="git_all_built_commits",
        display_name="All Built Commits",
        description="List of commit SHAs included in this build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.LIST_STRING,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
        output_format=OutputFormat.HASH_SEPARATED,
    ),
    "git_num_all_built_commits": FeatureDefinition(
        name="git_num_all_built_commits",
        display_name="Number of Built Commits",
        description="Count of commits included in this build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
    ),
    "git_prev_built_commit": FeatureDefinition(
        name="git_prev_built_commit",
        display_name="Previous Built Commit",
        description="SHA of last commit that was built",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
        nullable=True,
    ),
    "git_prev_commit_resolution_status": FeatureDefinition(
        name="git_prev_commit_resolution_status",
        display_name="Previous Commit Resolution",
        description="How previous commit was resolved",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
        valid_values=["build_found", "merge_found", "no_previous_build", "commit_not_found"],
    ),
    "tr_prev_build": FeatureDefinition(
        name="tr_prev_build",
        display_name="Previous Build ID",
        description="ID of the previous build for this commit chain",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
        nullable=True,
    ),
    # --- git_diff_features group ---
    "git_diff_src_churn": FeatureDefinition(
        name="git_diff_src_churn",
        display_name="Source Code Churn",
        description="Lines added + deleted in source files",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "git_diff_test_churn": FeatureDefinition(
        name="git_diff_test_churn",
        display_name="Test Code Churn",
        description="Lines added + deleted in test files",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_files_added": FeatureDefinition(
        name="gh_diff_files_added",
        display_name="Files Added",
        description="Number of files added in this build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_files_deleted": FeatureDefinition(
        name="gh_diff_files_deleted",
        display_name="Files Deleted",
        description="Number of files deleted in this build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_files_modified": FeatureDefinition(
        name="gh_diff_files_modified",
        display_name="Files Modified",
        description="Number of files modified in this build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_tests_added": FeatureDefinition(
        name="gh_diff_tests_added",
        display_name="Tests Added",
        description="Number of test cases added",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_tests_deleted": FeatureDefinition(
        name="gh_diff_tests_deleted",
        display_name="Tests Deleted",
        description="Number of test cases deleted",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_src_files": FeatureDefinition(
        name="gh_diff_src_files",
        display_name="Source Files Changed",
        description="Number of source files changed",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_doc_files": FeatureDefinition(
        name="gh_diff_doc_files",
        display_name="Doc Files Changed",
        description="Number of documentation files changed",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_diff_other_files": FeatureDefinition(
        name="gh_diff_other_files",
        display_name="Other Files Changed",
        description="Number of other files changed (not source or doc)",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    # --- Single git features ---
    "gh_num_commits_on_files_touched": FeatureDefinition(
        name="gh_num_commits_on_files_touched",
        display_name="Commits on Files Touched",
        description="Number of commits that touched files modified in this build (last N days)",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.BUILD_RUN],
    ),
    "gh_team_size": FeatureDefinition(
        name="gh_team_size",
        display_name="Team Size",
        description="Number of unique contributors in last 90 days",
        category=FeatureCategory.TEAM,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
    ),
    "gh_by_core_team_member": FeatureDefinition(
        name="gh_by_core_team_member",
        display_name="By Core Team Member",
        description="Whether build author is a core team member",
        category=FeatureCategory.TEAM,
        data_type=FeatureDataType.BOOLEAN,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
    ),
    "num_of_distinct_authors": FeatureDefinition(
        name="num_of_distinct_authors",
        display_name="Distinct Authors",
        description="Number of unique commit authors in this build",
        category=FeatureCategory.TEAM,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "total_number_of_revisions": FeatureDefinition(
        name="total_number_of_revisions",
        display_name="Total File Revisions",
        description="Total number of prior revisions on files touched by this build",
        category=FeatureCategory.COOPERATION,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    # =========================================================================
    # GITHUB FEATURES (github_features.py)
    # =========================================================================
    "gh_num_issue_comments": FeatureDefinition(
        name="gh_num_issue_comments",
        display_name="Issue Comments",
        description="Number of issue/discussion comments on the PR",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GITHUB_API, FeatureResource.BUILD_RUN],
    ),
    "gh_num_commit_comments": FeatureDefinition(
        name="gh_num_commit_comments",
        display_name="Commit Comments",
        description="Number of comments on commits in this build",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GITHUB_API],
    ),
    "gh_num_pr_comments": FeatureDefinition(
        name="gh_num_pr_comments",
        display_name="PR Review Comments",
        description="Number of code review comments on the PR",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GITHUB_API, FeatureResource.BUILD_RUN],
    ),
    "gh_description_complexity": FeatureDefinition(
        name="gh_description_complexity",
        display_name="Description Complexity",
        description="Word count of PR title + body",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GITHUB_API],
        nullable=True,
    ),
    # =========================================================================
    # REPO FEATURES (repo_features.py)
    # =========================================================================
    "gh_repo_age": FeatureDefinition(
        name="gh_repo_age",
        display_name="Repository Age",
        description="Repository age in days (from first commit to build commit)",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_HISTORY],
        unit="days",
    ),
    "gh_repo_num_commits": FeatureDefinition(
        name="gh_repo_num_commits",
        display_name="Total Commits",
        description="Total number of commits in repository history",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "gh_sloc": FeatureDefinition(
        name="gh_sloc",
        display_name="Source Lines of Code",
        description="Total source lines of code (excluding comments)",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_WORKTREE],
        nullable=True,
    ),
    "gh_test_lines_per_kloc": FeatureDefinition(
        name="gh_test_lines_per_kloc",
        display_name="Test Lines / KLOC",
        description="Test lines per 1000 lines of source code",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_WORKTREE],
        nullable=True,
    ),
    "gh_test_cases_per_kloc": FeatureDefinition(
        name="gh_test_cases_per_kloc",
        display_name="Test Cases / KLOC",
        description="Test cases per 1000 lines of source code",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_WORKTREE],
        nullable=True,
    ),
    "gh_asserts_case_per_kloc": FeatureDefinition(
        name="gh_asserts_case_per_kloc",
        display_name="Assertions / KLOC",
        description="Assertions per 1000 lines of source code",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_WORKTREE],
        nullable=True,
    ),
    # =========================================================================
    # HISTORY FEATURES (history_features.py)
    # =========================================================================
    "day_week": FeatureDefinition(
        name="day_week",
        display_name="Day of Week",
        description="Day of week when build was triggered (Monday-Sunday)",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_RUN],
        valid_values=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    ),
    "time_of_day": FeatureDefinition(
        name="time_of_day",
        display_name="Hour of Day",
        description="Hour when build was triggered (0-23 UTC)",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_RUN],
        valid_range=(0, 23),
    ),
    "prev_built_result": FeatureDefinition(
        name="prev_built_result",
        display_name="Previous Build Result",
        description="Outcome of the previous build (passed, failed, etc.)",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        nullable=True,
    ),
    "same_committer": FeatureDefinition(
        name="same_committer",
        display_name="Same Committer",
        description="Whether committer is same as previous build",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.BOOLEAN,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
    ),
    "time_since_prev_build": FeatureDefinition(
        name="time_since_prev_build",
        display_name="Time Since Previous Build",
        description="Days since previous build completed",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        unit="days",
        nullable=True,
    ),
    "committer_fail_history": FeatureDefinition(
        name="committer_fail_history",
        display_name="Committer Fail Rate",
        description="Overall fail rate of this committer",
        category=FeatureCategory.COMMITTER,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    "committer_recent_fail_history": FeatureDefinition(
        name="committer_recent_fail_history",
        display_name="Committer Recent Fail Rate",
        description="Fail rate in last N builds by this committer",
        category=FeatureCategory.COMMITTER,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    "committer_avg_exp": FeatureDefinition(
        name="committer_avg_exp",
        display_name="Committer Experience",
        description="Average experience of committers (builds per person)",
        category=FeatureCategory.COMMITTER,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
    ),
    "project_fail_history": FeatureDefinition(
        name="project_fail_history",
        display_name="Project Fail Rate",
        description="Overall fail rate of the project",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    "project_fail_recent": FeatureDefinition(
        name="project_fail_recent",
        display_name="Project Recent Fail Rate",
        description="Fail rate in last N builds of the project",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    # =========================================================================
    # DEVOPS FEATURES (devops_features.py)
    # =========================================================================
    "num_of_devops_files": FeatureDefinition(
        name="num_of_devops_files",
        display_name="DevOps Files Changed",
        description="Count of DevOps/CI configuration files changed in build",
        category=FeatureCategory.DEVOPS,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "devops_change_size": FeatureDefinition(
        name="devops_change_size",
        display_name="DevOps Change Size",
        description="Total lines changed in DevOps files",
        category=FeatureCategory.DEVOPS,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "devops_tools_used": FeatureDefinition(
        name="devops_tools_used",
        display_name="DevOps Tools",
        description="List of DevOps tools detected (Docker, K8s, etc.)",
        category=FeatureCategory.DEVOPS,
        data_type=FeatureDataType.LIST_STRING,
        required_resources=[FeatureResource.GIT_HISTORY],
        output_format=OutputFormat.COMMA_SEPARATED,
    ),
    # =========================================================================
    # LOG FEATURES (log_features.py)
    # =========================================================================
    "tr_log_frameworks_all": FeatureDefinition(
        name="tr_log_frameworks_all",
        display_name="Test Frameworks",
        description="List of detected test frameworks",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.LIST_STRING,
        required_resources=[FeatureResource.BUILD_LOGS],
        output_format=OutputFormat.COMMA_SEPARATED,
    ),
    "tr_log_tests_run_sum": FeatureDefinition(
        name="tr_log_tests_run_sum",
        display_name="Tests Run",
        description="Total tests run across all jobs",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_LOGS],
    ),
    "tr_log_tests_failed_sum": FeatureDefinition(
        name="tr_log_tests_failed_sum",
        display_name="Tests Failed",
        description="Total tests failed across all jobs",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_LOGS],
    ),
    "tr_log_tests_skipped_sum": FeatureDefinition(
        name="tr_log_tests_skipped_sum",
        display_name="Tests Skipped",
        description="Total tests skipped across all jobs",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_LOGS],
    ),
    "tr_log_tests_ok_sum": FeatureDefinition(
        name="tr_log_tests_ok_sum",
        display_name="Tests Passed",
        description="Total tests passed across all jobs",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_LOGS],
    ),
    "tr_log_tests_fail_rate": FeatureDefinition(
        name="tr_log_tests_fail_rate",
        display_name="Test Fail Rate",
        description="Failure rate (failed / run)",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.BUILD_LOGS],
        valid_range=(0.0, 1.0),
    ),
    "tr_log_testduration_sum": FeatureDefinition(
        name="tr_log_testduration_sum",
        display_name="Test Duration",
        description="Total test duration in seconds",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.BUILD_LOGS],
        unit="seconds",
    ),
    "tr_log_num_jobs": FeatureDefinition(
        name="tr_log_num_jobs",
        display_name="Number of Jobs",
        description="Number of job logs parsed from CI build",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.BUILD_LOGS],
    ),
    "tr_jobs": FeatureDefinition(
        name="tr_jobs",
        display_name="Job IDs",
        description="IDs of jobs in the CI build, comma-separated",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.STRING,
        required_resources=[FeatureResource.BUILD_LOGS],
    ),
    # =========================================================================
    # RISK PREDICTION FEATURES (risk_prediction_features.py)
    # =========================================================================
    # --- Temporal features ---
    "is_prev_failed": FeatureDefinition(
        name="is_prev_failed",
        display_name="Previous Build Failed",
        description="Whether the previous build failed",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.BOOLEAN,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        nullable=True,
    ),
    "prev_fail_streak": FeatureDefinition(
        name="prev_fail_streak",
        display_name="Previous Fail Streak",
        description="Number of consecutive failed builds before this one",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.INTEGER,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
    ),
    "fail_rate_last_10": FeatureDefinition(
        name="fail_rate_last_10",
        display_name="Fail Rate Last 10",
        description="Failure rate in last 10 builds",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    "avg_src_churn_last_5": FeatureDefinition(
        name="avg_src_churn_last_5",
        display_name="Avg Churn Last 5",
        description="Average source code churn in last 5 builds",
        category=FeatureCategory.BUILD_HISTORY,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
    ),
    # --- Churn features ---
    "change_entropy": FeatureDefinition(
        name="change_entropy",
        display_name="Change Entropy",
        description="Entropy of file changes in the build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_HISTORY],
    ),
    "files_modified_ratio": FeatureDefinition(
        name="files_modified_ratio",
        display_name="Files Modified Ratio",
        description="Ratio of modified files to total changed files",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_HISTORY],
        valid_range=(0.0, 1.0),
    ),
    "churn_ratio_vs_avg": FeatureDefinition(
        name="churn_ratio_vs_avg",
        display_name="Churn vs Average",
        description="Current churn relative to project average",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.RAW_BUILD_RUNS],
    ),
    # --- Author features ---
    "author_ownership": FeatureDefinition(
        name="author_ownership",
        display_name="Author Ownership",
        description="Percentage of project commits by this author",
        category=FeatureCategory.COMMITTER,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    "is_new_contributor": FeatureDefinition(
        name="is_new_contributor",
        display_name="New Contributor",
        description="Whether author has fewer than 5 builds in this project",
        category=FeatureCategory.COMMITTER,
        data_type=FeatureDataType.BOOLEAN,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
    ),
    "days_since_last_author_commit": FeatureDefinition(
        name="days_since_last_author_commit",
        display_name="Days Since Author's Last Commit",
        description="Days since this author's previous build",
        category=FeatureCategory.COMMITTER,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.RAW_BUILD_RUNS, FeatureResource.BUILD_RUN],
        unit="days",
        nullable=True,
    ),
    # --- Time features ---
    "build_time_sin": FeatureDefinition(
        name="build_time_sin",
        display_name="Build Time Sine",
        description="Sine encoding of build hour for cyclic representation",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.BUILD_RUN],
        valid_range=(-1.0, 1.0),
    ),
    "build_time_cos": FeatureDefinition(
        name="build_time_cos",
        display_name="Build Time Cosine",
        description="Cosine encoding of build hour for cyclic representation",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.BUILD_RUN],
        valid_range=(-1.0, 1.0),
    ),
    "build_hour_risk_score": FeatureDefinition(
        name="build_hour_risk_score",
        display_name="Build Hour Risk Score",
        description="Risk score based on build hour (higher at night)",
        category=FeatureCategory.METADATA,
        data_type=FeatureDataType.FLOAT,
        required_resources=[FeatureResource.BUILD_RUN],
        valid_range=(0.0, 1.0),
    ),
    # --- PR features ---
    "gh_has_bug_label": FeatureDefinition(
        name="gh_has_bug_label",
        display_name="Has Bug Label",
        description="Whether the PR has any bug-related labels",
        category=FeatureCategory.PR_INFO,
        data_type=FeatureDataType.BOOLEAN,
        required_resources=[FeatureResource.BUILD_RUN],
    ),
}


# HELPER FUNCTIONS
def get_feature_definition(name: str) -> Optional[FeatureDefinition]:
    """Get feature definition by name."""
    return FEATURE_REGISTRY.get(name)


def get_feature_data_type(name: str) -> str:
    """
    Get data type string for a feature.

    Returns:
        Data type string ('integer', 'float', 'string', etc.) or 'unknown'
    """
    defn = FEATURE_REGISTRY.get(name)
    if defn:
        return defn.data_type.value
    return "unknown"


def get_all_feature_names() -> List[str]:
    """Get list of all registered feature names."""
    return list(FEATURE_REGISTRY.keys())


def get_features_by_category(category: FeatureCategory) -> List[FeatureDefinition]:
    """Get all features in a specific category."""
    return [f for f in FEATURE_REGISTRY.values() if f.category == category]


def build_metadata_dict(name: str) -> Optional[Dict]:
    """
    Convert FeatureDefinition to dict format compatible with existing code.

    This helps with backwards compatibility.
    """
    defn = get_feature_definition(name)
    if not defn:
        return None

    return {
        "display_name": defn.display_name,
        "description": defn.description,
        "category": defn.category.value,
        "data_type": defn.data_type.value,
        "required_resources": [r.value for r in defn.required_resources],
        "nullable": defn.nullable,
        "unit": defn.unit,
        "output_format": defn.output_format.value if defn.output_format else None,
        "valid_range": defn.valid_range,
        "valid_values": defn.valid_values,
    }
