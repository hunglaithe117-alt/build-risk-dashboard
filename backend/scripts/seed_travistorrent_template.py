import logging

from app.database.mongo import get_database

# Import DEFAULT_FEATURES from constants (always extracted, not user-selectable)
from app.tasks.pipeline.constants import DEFAULT_FEATURES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# FEATURE DEFINITIONS BY GROUP
# These are explicitly listed for clarity. Update when adding new features.
# =============================================================================

# Build Log Features
FEATURES_BUILD_LOG = {
    "log_job_ids",
    "build_number",
    "build_duration_sec",
    "build_status",
    "build_trigger_sha",
    "log_jobs_count",
    "repo_languages_all",
    "log_tests_run",
    "log_tests_failed",
    "log_tests_skipped",
    "log_tests_passed",
    "log_tests_fail_rate",
    "log_test_duration_sec",
    "log_test_frameworks",
}

# Git Features (from git/*.py)
FEATURES_GIT = {
    # commit_info node
    "git_built_commits",
    "git_built_commits_count",
    "git_prev_commit_sha",
    "git_prev_commit_status",
    "history_prev_build_id",
    # diff_features node
    "git_diff_src_churn",
    "git_diff_test_churn",
    "git_diff_files_added",
    "git_diff_files_deleted",
    "git_diff_files_modified",
    "git_diff_tests_added",
    "git_diff_tests_deleted",
    "git_diff_src_files",
    "git_diff_doc_files",
    "git_diff_other_files",
    # file_touch_history node
    "git_file_commit_density",
    # team_membership node
    "team_size",
    "team_is_core_member",
}

# GitHub Features (from github/discussion.py)
FEATURES_GITHUB = {
    "pr_issue_comments",
    "pr_commit_comments",
    "pr_review_comments",
    "pr_description_words",
}

# Repo Snapshot Features (from repo/snapshot.py)
FEATURES_REPO = {
    "repo_age_days",
    "repo_total_commits",
    "repo_sloc",
    "repo_test_lines_per_kloc",
    "repo_test_cases_per_kloc",
    "repo_asserts_per_kloc",
    # Metadata
    "repo_full_name",
    "pr_is_triggered",
    "pr_created_at",
    "pr_number",
    "repo_language",
    "git_branch",
    "git_trigger_sha",
    "build_ci_provider",
    "build_started_at",
}

# All features combined
ALL_FEATURES = FEATURES_BUILD_LOG | FEATURES_GIT | FEATURES_GITHUB | FEATURES_REPO


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
