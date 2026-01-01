"""
Seed script for Risk Prediction feature template.

Creates a template with only the features required for the Bayesian LSTM risk model.
This minimal template ensures efficient ingestion by only fetching required resources.

Run with: python -m scripts.seed_prediction_template

Features are extracted directly from the trained model (hunglt/training.py).
"""

import logging

from app.database.mongo import get_database
from app.tasks.pipeline.constants import DEFAULT_FEATURES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# PREDICTION-REQUIRED FEATURES
# These match exactly what the Bayesian LSTM model uses for inference.
# Ref: hunglt/training.py, backend/app/services/risk_model/inference.py
# =============================================================================

# Temporal features (used in LSTM sequence - build history patterns)
TEMPORAL_FEATURES = {
    "is_prev_failed",
    "prev_fail_streak",
    "fail_rate_last_10",
    "avg_src_churn_last_5",
    "time_since_prev_build",
}

# Static features (point-in-time values for current build)
STATIC_FEATURES = {
    # Code churn features
    "git_diff_src_churn",
    "gh_diff_files_added",
    "gh_diff_files_deleted",
    "gh_diff_files_modified",
    "gh_diff_tests_added",
    "gh_diff_tests_deleted",
    "gh_diff_src_files",
    "gh_diff_doc_files",
    "gh_diff_other_files",
    "gh_num_commits_on_files_touched",
    "files_modified_ratio",
    "change_entropy",
    "churn_ratio_vs_avg",
    # Repository metrics
    "gh_sloc",
    "gh_repo_age",
    "gh_repo_num_commits",
    "gh_test_lines_per_kloc",
    "gh_test_cases_per_kloc",
    "gh_asserts_cases_per_kloc",  # Note: plural 'cases' to match model training
    # Team features
    "gh_team_size",
    "author_ownership",
    "is_new_contributor",
    "days_since_last_author_commit",
    # Test metrics from build logs
    "tr_log_num_jobs",
    "tr_log_tests_run_sum",
    "tr_log_tests_failed_sum",
    "tr_log_tests_skipped_sum",
    "tr_log_tests_ok_sum",
    "tr_log_testduration_sum",
    "tr_log_tests_fail_rate",
    "tr_duration",
    "tr_status_num",
    # Time features
    "build_time_sin",
    "build_time_cos",
    "build_hour_risk_score",
}

# Chain features needed for temporal resolution
CHAIN_FEATURES = {
    "tr_prev_build",  # Required for temporal feature chain
    "tr_status",  # Build status (for tr_status_num derivation)
}

# All features for prediction
ALL_PREDICTION_FEATURES = TEMPORAL_FEATURES | STATIC_FEATURES | CHAIN_FEATURES


def seed_prediction_template():
    """Create or update the Risk Prediction template with minimal features."""
    db = get_database()

    # Exclude default features from the selectable list (they're always included)
    selected_features = sorted(ALL_PREDICTION_FEATURES - DEFAULT_FEATURES)

    logger.info(f"Prediction features required: {len(ALL_PREDICTION_FEATURES)}")
    logger.info(f"Selectable features (excluding defaults): {len(selected_features)}")

    # Template document
    template = {
        "name": "Risk Prediction",
        "description": "Minimal feature set for Bayesian LSTM risk prediction model.",
        "feature_names": selected_features,
        "tags": ["prediction", "risk", "minimal", "bayesian-lstm"],
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

    # Print feature breakdown
    logger.info("   Feature breakdown:")
    logger.info(f"      temporal: {len(TEMPORAL_FEATURES)} features")
    logger.info(f"      static: {len(STATIC_FEATURES)} features")
    logger.info(f"      chain: {len(CHAIN_FEATURES)} features")

    # Print the actual features for reference
    logger.info("\n   Temporal features:")
    for f in sorted(TEMPORAL_FEATURES):
        logger.info(f"      - {f}")

    logger.info("\n   Static features:")
    for f in sorted(STATIC_FEATURES):
        logger.info(f"      - {f}")


if __name__ == "__main__":
    seed_prediction_template()
