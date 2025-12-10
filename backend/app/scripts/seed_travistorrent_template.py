"""
Seed script for TravisTorrent dataset template.

Creates a template with all available features from the code registry.
Run with: python -m app.scripts.seed_travistorrent_template

Feature names are explicitly listed here for clarity and maintainability.
When adding new features, add them to the appropriate FEATURES_* set below.
"""

import logging
from app.database.mongo import get_database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# FEATURE DEFINITIONS BY GROUP
# These are explicitly listed for clarity. Update when adding new features.
# =============================================================================

# Build Log Features
FEATURES_BUILD_LOG = {
    "tr_jobs",
    "tr_build_number",
    "tr_duration",
    "tr_status",
    "tr_original_commit",
    "tr_log_num_jobs",
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
FEATURES_GIT = {
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
FEATURES_GITHUB = {
    "gh_num_issue_comments",
    "gh_num_commit_comments",
    "gh_num_pr_comments",
    "gh_description_complexity",
}

# Repo Snapshot Features (from repo/snapshot.py)
FEATURES_REPO = {
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

# All features combined
ALL_FEATURES = FEATURES_BUILD_LOG | FEATURES_GIT | FEATURES_GITHUB | FEATURES_REPO

# Import DEFAULT_FEATURES from constants (always extracted, not user-selectable)
from app.pipeline.constants import DEFAULT_FEATURES


def seed_travistorrent_template():
    """Create or update the TravisTorrent dataset template with all features."""
    db = get_database()

    # Exclude default features from the selectable list (they're always included)
    selected_features = sorted(ALL_FEATURES - DEFAULT_FEATURES)

    logger.info(f"Total features available: {len(ALL_FEATURES)}")
    logger.info(f"Selectable features (excluding defaults): {len(selected_features)}")

    # Template document (simplified schema)
    template = {
        "name": "TravisTorrent Full",
        "description": "Complete feature set for CI/CD build prediction research.",
        "feature_names": selected_features,
        "tags": ["travistorrent", "ci-cd", "build-prediction", "full"],
        "source": "seed",
    }

    # Upsert by name
    result = db.dataset_templates.update_one(
        {"name": template["name"]},
        {"$set": template},
        upsert=True,
    )

    if result.upserted_id:
        logger.info(f"✅ Created new template: {template['name']}")
    else:
        logger.info(f"✅ Updated existing template: {template['name']}")

    logger.info(f"   Features included: {len(selected_features)}")

    # Print feature categories for verification
    logger.info("   Feature breakdown by group:")
    logger.info(f"      build_log: {len(FEATURES_BUILD_LOG)} features")
    logger.info(f"      git: {len(FEATURES_GIT)} features")
    logger.info(f"      github: {len(FEATURES_GITHUB)} features")
    logger.info(f"      repo: {len(FEATURES_REPO)} features")


if __name__ == "__main__":
    seed_travistorrent_template()
