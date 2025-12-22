"""Database index management for MongoDB collections."""

import logging

from pymongo.database import Database
from pymongo.errors import OperationFailure

logger = logging.getLogger(__name__)


def ensure_indexes(db: Database) -> None:
    """
    Ensure all required indexes exist.

    This function should be called on application startup to guarantee
    that all necessary indexes are in place for optimal query performance
    and data integrity.
    """
    _ensure_raw_build_runs_indexes(db)
    _ensure_raw_repositories_indexes(db)
    logger.info("Database indexes ensured successfully")


def _ensure_raw_build_runs_indexes(db: Database) -> None:
    """Create indexes for raw_build_runs collection."""
    collection = db.raw_build_runs

    # Compound unique index for business key deduplication
    # This ensures the same build from the same repo/provider is not duplicated
    # even when fetched from both model flow and dataset flow
    try:
        collection.create_index(
            [("raw_repo_id", 1), ("build_id", 1), ("provider", 1)],
            unique=True,
            background=True,
            name="raw_repo_build_provider_unique",
        )
        logger.debug("Created index: raw_repo_build_provider_unique")
    except OperationFailure as e:
        # Index may already exist with different options
        if "already exists" not in str(e):
            logger.warning(f"Failed to create raw_repo_build_provider_unique index: {e}")

    # Index for listing builds by repo (most common query)
    try:
        collection.create_index(
            [("raw_repo_id", 1), ("created_at", -1)],
            background=True,
            name="raw_repo_created_at_idx",
        )
        logger.debug("Created index: raw_repo_created_at_idx")
    except OperationFailure as e:
        if "already exists" not in str(e):
            logger.warning(f"Failed to create raw_repo_created_at_idx index: {e}")


def _ensure_raw_repositories_indexes(db: Database) -> None:
    """Create indexes for raw_repositories collection."""
    collection = db.raw_repositories

    # Unique index on github_repo_id for deduplication
    try:
        collection.create_index(
            [("github_repo_id", 1)],
            unique=True,
            sparse=True,  # Allow null values
            background=True,
            name="github_repo_id_unique",
        )
        logger.debug("Created index: github_repo_id_unique")
    except OperationFailure as e:
        if "already exists" not in str(e):
            logger.warning(f"Failed to create github_repo_id_unique index: {e}")

    # Index on full_name for lookups
    try:
        collection.create_index(
            [("full_name", 1)],
            background=True,
            name="full_name_idx",
        )
        logger.debug("Created index: full_name_idx")
    except OperationFailure as e:
        if "already exists" not in str(e):
            logger.warning(f"Failed to create full_name_idx index: {e}")
