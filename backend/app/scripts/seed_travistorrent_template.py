"""
Seed script for TravisTorrent dataset template.

Creates a template with all available features from the code registry.
Run with: python -m app.scripts.seed_travistorrent_template
"""

import logging
from app.database.mongo import get_database
from app.pipeline.core.registry import feature_registry
from app.pipeline.constants import DEFAULT_FEATURES

# Ensure all feature nodes are registered
import app.pipeline  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_travistorrent_template():
    """Create or update the TravisTorrent dataset template with all features."""
    db = get_database()

    # Get all features from the code registry (excluding default features)
    all_nodes = feature_registry.get_all(enabled_only=True)

    all_features = set()
    for meta in all_nodes.values():
        all_features.update(meta.provides)

    # Exclude default features (they're always included automatically)
    selected_features = sorted(all_features - DEFAULT_FEATURES)

    logger.info(f"Found {len(selected_features)} features from code registry")

    # Template document
    template = {
        "name": "TravisTorrent Full",
        "description": "Complete TravisTorrent dataset template with all available features for CI/CD build prediction research.",
        "file_name": "travistorrent_full.csv",
        "source": "seed",
        "rows": 0,
        "size_mb": 0.0,
        "columns": [],
        "mapped_fields": {
            "build_id_field": "tr_build_id",
            "commit_sha_field": "git_trigger_commit",
            "branch_field": "git_branch",
            "status_field": "tr_status",
            "duration_field": "tr_duration",
            "timestamp_field": "gh_build_started_at",
        },
        "stats": {
            "pass_count": 0,
            "fail_count": 0,
            "pass_rate": 0.0,
        },
        "tags": ["travistorrent", "ci-cd", "build-prediction", "full"],
        "selected_template": None,
        "selected_features": selected_features,
        "preview": [],
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
    by_prefix = {}
    for feat in selected_features:
        prefix = feat.split("_")[0]
        by_prefix[prefix] = by_prefix.get(prefix, 0) + 1

    logger.info("   Feature breakdown by prefix:")
    for prefix, count in sorted(by_prefix.items()):
        logger.info(f"      {prefix}: {count}")


if __name__ == "__main__":
    seed_travistorrent_template()
