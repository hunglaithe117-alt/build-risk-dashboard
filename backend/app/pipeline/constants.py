from typing import Set

# =============================================================================
# FEATURE DEFINITIONS BY GROUP
# =============================================================================

# Build Log Features (from build_log/*.py)
FEATURES_BUILD_LOG: Set[str] = {
    "tr_log_lan_all",
    "tr_log_tests_run_sum",
    "tr_log_tests_failed_sum",
    "tr_log_tests_skipped_sum",
    "tr_log_tests_ok_sum",
    "tr_log_tests_fail_rate",
    "tr_log_testduration_sum",
    "tr_log_frameworks_all",
}

# Git Features (from git/*.py)
FEATURES_GIT: Set[str] = {
    # commit_info node
    "git_all_built_commits",
    "git_num_all_built_commits",
    "git_prev_built_commit",
    "git_prev_commit_resolution_status",
    "tr_prev_build",
    # diff_features node
    "git_diff_src_churn",
    "git_diff_test_churn",
    "gh_diff_files_added",
    "gh_diff_files_deleted",
    "gh_diff_files_modified",
    "gh_diff_tests_added",
    "gh_diff_tests_deleted",
    "gh_diff_src_files",
    "gh_diff_doc_files",
    "gh_diff_other_files",
    # file_touch_history node
    "gh_num_commits_on_files_touched",
    # team_membership node
    "gh_team_size",
    "gh_by_core_team_member",
}

# GitHub Features (from github/discussion.py)
FEATURES_GITHUB: Set[str] = {
    "gh_num_issue_comments",
    "gh_num_commit_comments",
    "gh_num_pr_comments",
    "gh_description_complexity",
}

# Repo Snapshot Features (from repo/snapshot.py)
FEATURES_REPO: Set[str] = {
    "gh_repo_age",
    "gh_repo_num_commits",
    "gh_sloc",
    "gh_test_lines_per_kloc",
    "gh_test_cases_per_kloc",
    "gh_asserts_case_per_kloc",
    # Metadata
    "gh_project_name",
    "gh_is_pr",
    "gh_pr_created_at",
    "gh_pull_req_num",
    "gh_lang",
    "git_branch",
    "git_trigger_commit",
    "ci_provider",
    "gh_build_started_at",
}

# All TravisTorrent features for Bayesian model
TRAVISTORRENT_FEATURES: Set[str] = (
    FEATURES_BUILD_LOG | FEATURES_GIT | FEATURES_GITHUB | FEATURES_REPO
)

# Default features always extracted (required for mapping/identification)
# These are not selectable in custom feature wizard - always included automatically
DEFAULT_FEATURES: Set[str] = {
    "tr_build_id",
    "gh_project_name",
}

# All features including defaults
ALL_FEATURES: Set[str] = TRAVISTORRENT_FEATURES | DEFAULT_FEATURES


def get_travistorrent_feature_list() -> list[str]:
    """Get sorted list of TravisTorrent features for extraction."""
    return sorted(TRAVISTORRENT_FEATURES)


def get_feature_count() -> int:
    """Get total number of extractable TravisTorrent features."""
    return len(TRAVISTORRENT_FEATURES)
