"""
Seed script for Risk Prediction feature template.

Creates a template with only the features required for the Bayesian LSTM risk model.
This minimal template ensures efficient ingestion by only fetching required resources.

Run with: python -m scripts.seed_prediction_template

Features are extracted directly from RiskModelService's TEMPORAL_FEATURES and STATIC_FEATURES.
"""

import logging

from app.database.mongo import get_database
from app.tasks.pipeline.constants import DEFAULT_FEATURES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# PREDICTION-REQUIRED FEATURES
# These match exactly what RiskModelService uses for inference.
# =============================================================================

# Temporal features (used in LSTM sequence)
TEMPORAL_FEATURES = {
    "is_prev_failed",
    "prev_fail_streak",
    "fail_rate_last_10",
    "avg_src_churn_last_5",
    "time_since_prev_build",
}

# Static features (used as point-in-time values)
STATIC_FEATURES = {
    # Git/Churn features
    "git_diff_src_churn",
    "change_entropy",
    "files_modified_ratio",
    "churn_ratio_vs_avg",
    # Repo metrics
    "gh_sloc",
    "gh_repo_age",
    "gh_test_lines_per_kloc",
    "gh_team_size",
    # Author features
    "author_ownership",
    "is_new_contributor",
    "days_since_last_author_commit",
    # PR/Build metadata
    "gh_is_pr",
    "gh_has_bug_label",
    # Test/Duration features
    "tr_log_tests_fail_rate",
    "tr_duration",
    # Time features
    "build_time_sin",
    "build_time_cos",
    "build_hour_risk_score",
}

# Additional features needed for temporal chain resolution
CHAIN_FEATURES = {
    "tr_prev_build",  # Required for temporal feature chain
    "tr_status",  # Build status
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
