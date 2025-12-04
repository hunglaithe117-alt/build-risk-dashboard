"""
Feature Definitions Seed Data.

Run this script to seed the feature_definitions collection in MongoDB.

Usage:
    python -m app.seeds.feature_definitions
"""

from datetime import datetime, timezone
from typing import List

from app.models.entities.feature_definition import (
    FeatureDefinition,
    FeatureSource,
    FeatureDataType,
    FeatureCategory,
)


def get_feature_definitions() -> List[FeatureDefinition]:
    """Get all feature definitions for seeding."""
    
    features = []
    
    # =========================================================================
    # BUILD LOG FEATURES (from build_log_features node)
    # =========================================================================
    build_log_features = [
        FeatureDefinition(
            name="tr_build_id",
            display_name="Build ID",
            description="Unique identifier for the build (workflow run ID)",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="tr_build_number",
            display_name="Build Number",
            description="Sequential build number in the repository",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_original_commit",
            display_name="Original Commit SHA",
            description="The commit SHA that triggered the build",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="tr_status",
            display_name="Build Status",
            description="Final status of the build (passed/failed/cancelled)",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,  # Target variable
        ),
        FeatureDefinition(
            name="tr_duration",
            display_name="Build Duration",
            description="Total duration of the build in seconds",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.FLOAT,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_jobs",
            display_name="Job IDs",
            description="List of job IDs in the build",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.LIST_INTEGER,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="tr_log_num_jobs",
            display_name="Number of Jobs",
            description="Total number of jobs in the build",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_log_lan_all",
            display_name="Detected Languages",
            description="Programming languages detected in build logs",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.LIST_STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="tr_log_frameworks_all",
            display_name="Test Frameworks",
            description="Test frameworks detected in build logs",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.LIST_STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="tr_log_tests_run_sum",
            display_name="Total Tests Run",
            description="Total number of tests executed",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_log_tests_ok_sum",
            display_name="Tests Passed",
            description="Number of tests that passed",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_log_tests_failed_sum",
            display_name="Tests Failed",
            description="Number of tests that failed",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_log_tests_skipped_sum",
            display_name="Tests Skipped",
            description="Number of tests that were skipped",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_log_tests_fail_rate",
            display_name="Test Failure Rate",
            description="Ratio of failed tests to total tests run",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.FLOAT,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="tr_log_testduration_sum",
            display_name="Total Test Duration",
            description="Total duration of all tests in seconds",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.BUILD_LOG,
            extractor_node="build_log_features",
            depends_on_features=[],
            depends_on_resources=["log_storage", "workflow_run"],
            data_type=FeatureDataType.FLOAT,
            is_active=True,
            is_ml_feature=True,
        ),
    ]
    features.extend(build_log_features)
    
    # =========================================================================
    # GIT COMMIT INFO FEATURES (from git_commit_info node)
    # =========================================================================
    git_commit_features = [
        FeatureDefinition(
            name="git_all_built_commits",
            display_name="All Built Commits",
            description="List of all commit SHAs included in this build",
            category=FeatureCategory.GIT_HISTORY,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_commit_info",
            depends_on_features=[],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.LIST_STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="git_num_all_built_commits",
            display_name="Number of Built Commits",
            description="Count of commits included in this build",
            category=FeatureCategory.GIT_HISTORY,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_commit_info",
            depends_on_features=[],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="git_prev_built_commit",
            display_name="Previous Built Commit",
            description="SHA of the previous successfully built commit",
            category=FeatureCategory.GIT_HISTORY,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_commit_info",
            depends_on_features=[],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="git_prev_commit_resolution_status",
            display_name="Previous Commit Resolution Status",
            description="Status of finding previous commit (found/first_build/not_in_lineage)",
            category=FeatureCategory.GIT_HISTORY,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_commit_info",
            depends_on_features=[],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="tr_prev_build",
            display_name="Previous Build Run ID",
            description="Workflow run ID of the previous build",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_commit_info",
            depends_on_features=[],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=False,
        ),
    ]
    features.extend(git_commit_features)
    
    # =========================================================================
    # GIT DIFF FEATURES (from git_diff_features node)
    # =========================================================================
    git_diff_features = [
        FeatureDefinition(
            name="git_diff_src_churn",
            display_name="Source Code Churn",
            description="Lines added + deleted in source files",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="git_diff_test_churn",
            display_name="Test Code Churn",
            description="Lines added + deleted in test files",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_src_files",
            display_name="Source Files Changed",
            description="Number of source files modified",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_doc_files",
            display_name="Doc Files Changed",
            description="Number of documentation files modified",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_other_files",
            display_name="Other Files Changed",
            description="Number of other files modified (config, etc.)",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_files_added",
            display_name="Files Added",
            description="Number of new files added",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_files_deleted",
            display_name="Files Deleted",
            description="Number of files removed",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_files_modified",
            display_name="Files Modified",
            description="Number of existing files modified",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_tests_added",
            display_name="Test Files Added",
            description="Number of new test files added",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_diff_tests_deleted",
            display_name="Test Files Deleted",
            description="Number of test files removed",
            category=FeatureCategory.GIT_DIFF,
            source=FeatureSource.GIT_REPO,
            extractor_node="git_diff_features",
            depends_on_features=["git_all_built_commits", "git_prev_built_commit"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
    ]
    features.extend(git_diff_features)
    
    # =========================================================================
    # TEAM STATS FEATURES (from team_stats_features node)
    # =========================================================================
    team_features = [
        FeatureDefinition(
            name="gh_team_size",
            display_name="Team Size",
            description="Number of unique contributors to files in this commit",
            category=FeatureCategory.TEAM,
            source=FeatureSource.GIT_REPO,
            extractor_node="team_stats_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_by_core_team_member",
            display_name="By Core Team Member",
            description="Whether the commit author is a core team member (>10 commits)",
            category=FeatureCategory.TEAM,
            source=FeatureSource.GIT_REPO,
            extractor_node="team_stats_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.BOOLEAN,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_num_commits_on_files_touched",
            display_name="Prior Commits on Files",
            description="Total prior commits on files touched in this build",
            category=FeatureCategory.TEAM,
            source=FeatureSource.GIT_REPO,
            extractor_node="team_stats_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["git_repo"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
    ]
    features.extend(team_features)
    
    # =========================================================================
    # GITHUB DISCUSSION FEATURES (from github_discussion_features node)
    # =========================================================================
    github_features = [
        FeatureDefinition(
            name="gh_num_pr_comments",
            display_name="PR Comments",
            description="Number of comments on the pull request",
            category=FeatureCategory.DISCUSSION,
            source=FeatureSource.GITHUB_API,
            extractor_node="github_discussion_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["github_client", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_num_issue_comments",
            display_name="Issue Comments",
            description="Number of issue comments related to the build",
            category=FeatureCategory.DISCUSSION,
            source=FeatureSource.GITHUB_API,
            extractor_node="github_discussion_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["github_client", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_num_commit_comments",
            display_name="Commit Comments",
            description="Number of comments on commits in the build",
            category=FeatureCategory.DISCUSSION,
            source=FeatureSource.GITHUB_API,
            extractor_node="github_discussion_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["github_client", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_description_complexity",
            display_name="Description Complexity",
            description="Complexity score of PR/commit description (word count)",
            category=FeatureCategory.DISCUSSION,
            source=FeatureSource.GITHUB_API,
            extractor_node="github_discussion_features",
            depends_on_features=["git_all_built_commits"],
            depends_on_resources=["github_client", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
    ]
    features.extend(github_features)
    
    # =========================================================================
    # REPO SNAPSHOT FEATURES (from repo_snapshot_features node)
    # =========================================================================
    repo_features = [
        FeatureDefinition(
            name="gh_project_name",
            display_name="Project Name",
            description="Name of the repository",
            category=FeatureCategory.METADATA,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="gh_lang",
            display_name="Primary Language",
            description="Main programming language of the repository",
            category=FeatureCategory.METADATA,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="ci_provider",
            display_name="CI Provider",
            description="Continuous Integration provider (github_actions, etc.)",
            category=FeatureCategory.METADATA,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="git_branch",
            display_name="Git Branch",
            description="Branch name of the build",
            category=FeatureCategory.GIT_HISTORY,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="git_trigger_commit",
            display_name="Trigger Commit",
            description="The commit SHA that triggered the workflow",
            category=FeatureCategory.GIT_HISTORY,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="gh_is_pr",
            display_name="Is Pull Request",
            description="Whether this build is for a pull request",
            category=FeatureCategory.PR_INFO,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.BOOLEAN,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_pull_req_num",
            display_name="Pull Request Number",
            description="Pull request number if this is a PR build",
            category=FeatureCategory.PR_INFO,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="gh_pr_created_at",
            display_name="PR Created At",
            description="Timestamp when the pull request was created",
            category=FeatureCategory.PR_INFO,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="gh_build_started_at",
            display_name="Build Started At",
            description="Timestamp when the build started",
            category=FeatureCategory.BUILD_LOG,
            source=FeatureSource.GITHUB_API,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.STRING,
            is_active=True,
            is_ml_feature=False,
        ),
        FeatureDefinition(
            name="gh_repo_age",
            display_name="Repository Age",
            description="Age of the repository in days",
            category=FeatureCategory.REPO_SNAPSHOT,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_repo_num_commits",
            display_name="Repository Commits",
            description="Total number of commits in the repository",
            category=FeatureCategory.REPO_SNAPSHOT,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_sloc",
            display_name="Source Lines of Code",
            description="Total source lines of code in the repository",
            category=FeatureCategory.REPO_SNAPSHOT,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.INTEGER,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_test_lines_per_kloc",
            display_name="Test Lines per KLOC",
            description="Test lines per thousand lines of source code",
            category=FeatureCategory.REPO_SNAPSHOT,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.FLOAT,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_test_cases_per_kloc",
            display_name="Test Cases per KLOC",
            description="Number of test cases per thousand lines of source code",
            category=FeatureCategory.REPO_SNAPSHOT,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.FLOAT,
            is_active=True,
            is_ml_feature=True,
        ),
        FeatureDefinition(
            name="gh_asserts_case_per_kloc",
            display_name="Assertions per KLOC",
            description="Number of assertions per thousand lines of source code",
            category=FeatureCategory.REPO_SNAPSHOT,
            source=FeatureSource.GIT_REPO,
            extractor_node="repo_snapshot_features",
            depends_on_features=[],
            depends_on_resources=["git_repo", "workflow_run"],
            data_type=FeatureDataType.FLOAT,
            is_active=True,
            is_ml_feature=True,
        ),
    ]
    features.extend(repo_features)
    
    return features


def seed_feature_definitions(db) -> int:
    """
    Seed feature definitions into MongoDB.
    
    Returns:
        Number of features upserted
    """
    from app.repositories.feature_definition import FeatureDefinitionRepository
    
    repo = FeatureDefinitionRepository(db)
    features = get_feature_definitions()
    
    count = repo.bulk_upsert(features)
    return count


def run_seed():
    """Run the seed script directly."""
    from app.database.mongo import get_database
    
    db = get_database()
    count = seed_feature_definitions(db)
    
    features = get_feature_definitions()
    ml_features = [f for f in features if f.is_ml_feature]
    
    print(f"✅ Seeded {count} feature definitions")
    print(f"   Total features: {len(features)}")
    print(f"   ML features: {len(ml_features)}")
    
    # Count by category
    from collections import Counter
    categories = Counter(
        f.category.value if hasattr(f.category, 'value') else f.category 
        for f in features
    )
    print("\n   By category:")
    for cat, cnt in sorted(categories.items()):
        print(f"     - {cat}: {cnt}")
    
    # Count by extractor node
    nodes = Counter(f.extractor_node for f in features)
    print("\n   By extractor node:")
    for node, cnt in sorted(nodes.items()):
        print(f"     - {node}: {cnt}")


if __name__ == "__main__":
    run_seed()
