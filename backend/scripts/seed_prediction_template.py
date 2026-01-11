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
    "history_prev_failed",
    "history_fail_streak",
    "history_fail_rate_10",
    "history_avg_churn_5",
    "history_days_since_prev",
}

# Static features (point-in-time values for current build)
STATIC_FEATURES = {
    # Code churn features
    "git_diff_src_churn",
    "git_diff_files_added",
    "git_diff_files_deleted",
    "git_diff_files_modified",
    "git_diff_tests_added",
    "git_diff_tests_deleted",
    "git_diff_src_files",
    "git_diff_doc_files",
    "git_diff_other_files",
    "git_file_commit_density",
    "git_files_modified_ratio",
    "git_change_entropy",
    "git_churn_vs_avg",
    # Repository metrics
    "repo_sloc",
    "repo_age_days",
    "repo_total_commits",
    "repo_test_lines_per_kloc",
    "repo_test_cases_per_kloc",
    "repo_asserts_per_kloc",
    # Team features
    "team_size",
    "author_ownership",
    "author_is_new",
    "author_days_since_commit",
    # Test metrics from build logs
    "log_jobs_count",
    "log_tests_run",
    "log_tests_failed",
    "log_tests_skipped",
    "log_tests_passed",
    "log_test_duration_sec",
    "log_tests_fail_rate",
    "build_duration_sec",
    "build_status_num",
    # Time features
    "build_hour_sin",
    "build_hour_cos",
    "build_hour_risk",
}

# Chain features needed for temporal resolution
CHAIN_FEATURES = {
    "history_prev_build_id",  # Required for temporal feature chain
    "build_status",  # Build status (for tr_status_num derivation)
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
