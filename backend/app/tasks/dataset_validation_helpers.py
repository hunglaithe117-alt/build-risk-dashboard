"""
Dataset Validation Helpers - Utilities for distributed validation processing.

Contains helper functions for:
- Chunked CSV reading
- Build grouping by repo
- Batch database operations
- Redis stats management
"""

import logging
from typing import Any, Dict, Generator, List, Optional

import pandas as pd
import redis

from app.config import settings
from app.entities import DatasetBuild
from app.repositories.dataset_build_repository import DatasetBuildRepository

logger = logging.getLogger(__name__)

# Redis keys for validation stats
REDIS_VALIDATION_PREFIX = "dataset_validation:"


def get_redis_client() -> redis.Redis:
    """Get Redis client for stats tracking."""
    return redis.from_url(settings.REDIS_URL)


def init_validation_stats(dataset_id: str, total_repos: int, total_builds: int) -> None:
    """
    Initialize Redis counters for a validation job.

    Args:
        dataset_id: Dataset being validated
        total_repos: Total unique repos to validate
        total_builds: Total builds to validate
    """
    r = get_redis_client()
    prefix = f"{REDIS_VALIDATION_PREFIX}{dataset_id}"

    # Set initial counters
    pipe = r.pipeline()
    pipe.set(f"{prefix}:total_repos", total_repos)
    pipe.set(f"{prefix}:total_builds", total_builds)
    pipe.set(f"{prefix}:repos_valid", 0)
    pipe.set(f"{prefix}:repos_not_found", 0)
    pipe.set(f"{prefix}:repos_private", 0)
    pipe.set(f"{prefix}:builds_found", 0)
    pipe.set(f"{prefix}:builds_not_found", 0)
    pipe.set(f"{prefix}:builds_filtered", 0)
    pipe.set(f"{prefix}:chunks_completed", 0)
    pipe.set(f"{prefix}:total_chunks", 0)
    pipe.expire(f"{prefix}:total_repos", 86400)  # 24h TTL
    pipe.execute()


def increment_validation_stat(dataset_id: str, stat_name: str, amount: int = 1) -> int:
    """
    Increment a validation stat counter in Redis.

    Args:
        dataset_id: Dataset being validated
        stat_name: Name of stat (repos_valid, builds_found, etc.)
        amount: Amount to increment

    Returns:
        New value after increment
    """
    r = get_redis_client()
    key = f"{REDIS_VALIDATION_PREFIX}{dataset_id}:{stat_name}"
    return r.incrby(key, amount)


def get_validation_stats(dataset_id: str) -> Dict[str, int]:
    """
    Get all validation stats from Redis.

    Args:
        dataset_id: Dataset being validated

    Returns:
        Dict with all stat values
    """
    r = get_redis_client()
    prefix = f"{REDIS_VALIDATION_PREFIX}{dataset_id}"

    stats = {}
    stat_names = [
        "total_repos",
        "total_builds",
        "repos_valid",
        "repos_not_found",
        "repos_private",
        "builds_found",
        "builds_not_found",
        "builds_filtered",
        "chunks_completed",
        "total_chunks",
    ]

    for name in stat_names:
        value = r.get(f"{prefix}:{name}")
        stats[name] = int(value) if value else 0

    return stats


def cleanup_validation_stats(dataset_id: str) -> None:
    """Delete validation stats from Redis after completion."""
    r = get_redis_client()
    prefix = f"{REDIS_VALIDATION_PREFIX}{dataset_id}"

    keys = r.keys(f"{prefix}:*")
    if keys:
        r.delete(*keys)


def is_validation_cancelled(dataset_id: str) -> bool:
    """Check if validation was cancelled via Redis flag."""
    r = get_redis_client()
    return r.get(f"dataset_validation:{dataset_id}:cancelled") == b"1"


def read_csv_chunks(
    file_path: str,
    build_id_column: str,
    repo_name_column: str,
    ci_provider_column: Optional[str] = None,
    single_ci_provider: Optional[str] = None,
    chunk_size: Optional[int] = None,
) -> Generator[pd.DataFrame, None, None]:
    """
    Read CSV file in chunks for memory-efficient processing.

    Args:
        file_path: Path to CSV file
        build_id_column: Column name for build IDs
        repo_name_column: Column name for repo names
        ci_provider_column: Optional column for CI provider
        single_ci_provider: Single CI provider if not using column
        chunk_size: Rows per chunk (defaults to settings.VALIDATION_CSV_CHUNK_SIZE)

    Yields:
        DataFrames with standardized columns (build_id, repo_name, ci_provider)
    """
    if chunk_size is None:
        chunk_size = settings.VALIDATION_CSV_CHUNK_SIZE

    # Determine columns to read
    usecols = [build_id_column, repo_name_column]
    if ci_provider_column:
        usecols.append(ci_provider_column)

    for chunk_df in pd.read_csv(
        file_path,
        dtype=str,
        usecols=usecols,
        chunksize=chunk_size,
    ):
        # Rename to standard columns
        rename_map = {
            build_id_column: "build_id",
            repo_name_column: "repo_name",
        }
        if ci_provider_column:
            rename_map[ci_provider_column] = "ci_provider"

        chunk_df = chunk_df.rename(columns=rename_map)

        # Add ci_provider if single mode
        if single_ci_provider and not ci_provider_column:
            chunk_df["ci_provider"] = single_ci_provider

        # Clean data
        chunk_df = chunk_df.dropna(subset=["build_id", "repo_name"])
        chunk_df["build_id"] = chunk_df["build_id"].astype(str).str.strip()
        chunk_df["repo_name"] = chunk_df["repo_name"].astype(str).str.strip()

        # Filter invalid repo format
        valid_pattern = r"^[\w.-]+/[\w.-]+$"
        chunk_df = chunk_df[chunk_df["repo_name"].str.match(valid_pattern, na=False)]

        # Filter to only supported CI providers
        from app.ci_providers.factory import CIProviderRegistry

        supported_providers = {p.value for p in CIProviderRegistry.get_all_types()}
        if "ci_provider" in chunk_df.columns:
            original_count = len(chunk_df)
            chunk_df = chunk_df[chunk_df["ci_provider"].isin(supported_providers)]
            filtered_count = original_count - len(chunk_df)
            if filtered_count > 0:
                logger.debug(f"Filtered {filtered_count} rows with unsupported CI providers")

        yield chunk_df


def group_builds_by_repo(
    df: pd.DataFrame,
) -> Dict[str, List[Dict[str, str]]]:
    """
    Group builds by repository name.

    Args:
        df: DataFrame with build_id, repo_name, ci_provider columns

    Returns:
        Dict mapping repo_name to list of build info dicts
    """
    repo_builds: Dict[str, List[Dict[str, str]]] = {}

    for _, row in df.iterrows():
        repo_name = row["repo_name"]
        if repo_name not in repo_builds:
            repo_builds[repo_name] = []

        repo_builds[repo_name].append(
            {
                "build_id": row["build_id"],
                "ci_provider": row.get("ci_provider", "github_actions"),
            }
        )

    return repo_builds


def chunk_dict(
    d: Dict[str, Any],
    chunk_size: int,
) -> Generator[Dict[str, Any], None, None]:
    """
    Split a dictionary into smaller chunks.

    Args:
        d: Dictionary to chunk
        chunk_size: Max items per chunk

    Yields:
        Smaller dictionaries
    """
    items = list(d.items())
    for i in range(0, len(items), chunk_size):
        yield dict(items[i : i + chunk_size])


def chunk_list(
    lst: List[Any],
    chunk_size: int,
) -> Generator[List[Any], None, None]:
    """
    Split a list into smaller chunks.

    Args:
        lst: List to chunk
        chunk_size: Max items per chunk

    Yields:
        Smaller lists
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def batch_create_dataset_builds(
    dataset_build_repo: DatasetBuildRepository,
    builds: List[DatasetBuild],
) -> int:
    """
    Batch insert DatasetBuild records.

    Args:
        dataset_build_repo: Repository for DatasetBuild
        builds: List of DatasetBuild entities to insert

    Returns:
        Number of records inserted
    """
    if not builds:
        return 0

    # Convert entities to dicts for bulk insert
    docs = []
    for build in builds:
        doc = build.model_dump(by_alias=True, exclude_none=True)
        if "_id" in doc and doc["_id"] is None:
            del doc["_id"]
        docs.append(doc)

    result = dataset_build_repo.collection.insert_many(docs)
    return len(result.inserted_ids)


def calculate_progress(
    chunks_completed: int,
    total_chunks: int,
) -> int:
    """Calculate validation progress percentage."""
    if total_chunks == 0:
        return 0
    return min(int((chunks_completed / total_chunks) * 100), 99)
