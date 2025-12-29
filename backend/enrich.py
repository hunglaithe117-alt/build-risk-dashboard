"""
GitHub Data Enrichment Pipeline
================================
Main script to enrich TravisTorrent builds data with GitHub/Git features.

Usage:
    python enrich.py --input builds.csv --output enriched.csv --tokens tokens.txt
"""

import argparse
import gc
import logging
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd
from github_client import GitHubAPIClient, TokenManager
from tqdm import tqdm

from feature_extractors import (
    calculate_churn_ratio_vs_avg,
    calculate_files_modified_ratio,
    calculate_time_since_prev_build,
    check_has_issue_reference,
    check_is_merge_commit,
    check_is_new_contributor,
    extract_author_ownership,
    extract_author_total_commits,
    extract_build_time_features,
    extract_change_entropy,
    # New features
    extract_commit_message_length,
    extract_days_since_last_author_commit,
    extract_file_change_frequency,
    extract_pr_extra_features,
    extract_pr_features,
    extract_prev_build_features,
    parse_datetime,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG = {
    "repos_dir": "repos",  # Directory to clone repos
    "cache_dir": "cache",  # Cache for API responses
    "batch_size": 300,  # Process in batches
    "max_workers": 4,  # Parallel workers
    "cleanup_repos": True,  # Delete repos after processing
    "db_path": "enrichment.db",  # DuckDB database file
}

# New features to add
NEW_FEATURES = [
    # Source Code Stream
    "change_entropy",
    "file_change_frequency",
    "churn_ratio_vs_avg",
    # Test & Coverage Stream
    "prev_tr_status",
    "is_prev_failed",
    "prev_fail_streak",
    "fail_rate_last_10",
    "avg_src_churn_last_5",
    # Team Activity Stream
    "gh_num_reviewers",
    "gh_num_approvals",
    "gh_review_sentiment",
    "gh_time_to_first_review",
    "gh_linked_issues_count",
    "gh_has_bug_label",
    "author_ownership",
    "is_new_contributor",
    # Monitoring Stream
    "build_time_sin",
    "build_time_cos",
    "build_hour_risk_score",
    "time_since_prev_build",
    # Additional Features (Git-based)
    "commit_message_length",
    "has_issue_reference",
    "files_modified_ratio",
    "is_merge_commit",
    "days_since_last_author_commit",
    "author_total_commits",
    # Additional Features (PR-based)
    "pr_age_hours",
    "pr_num_commits",
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def init_db(db_path: str):
    """Initialize DuckDB database and create table if not exists."""
    con = duckdb.connect(db_path)
    # Check if table exists
    tables = con.sql("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]

    if "enriched_builds" not in table_names:
        logger.info("Created new DuckDB table: enriched_builds")
        # We don't define schema strictly, DuckDB infers it

    con.close()


def get_processed_ids(db_path: str) -> set:
    """Get set of already processed tr_build_ids from DuckDB."""
    con = duckdb.connect(db_path)
    try:
        # Check if table exists
        tables = con.sql("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        if "enriched_builds" not in table_names:
            return set()

        result = con.sql("SELECT tr_build_id FROM enriched_builds").fetchall()
        return set(r[0] for r in result)
    except Exception as e:
        logger.warning(f"Could not read processed IDs: {e}")
        return set()
    finally:
        con.close()


def save_to_db(df: pd.DataFrame, db_path: str):
    """Save DataFrame to DuckDB table."""
    if df.empty:
        return

    con = duckdb.connect(db_path)
    try:
        # If table exists, append. If not, create.
        con.sql("CREATE TABLE IF NOT EXISTS enriched_builds AS SELECT * FROM df LIMIT 0")
        con.sql("INSERT INTO enriched_builds SELECT * FROM df")
        logger.info(f"✅ Saved {len(df)} rows to DuckDB")
    except Exception as e:
        logger.error(f"Failed to save to DuckDB: {e}")
    finally:
        con.close()


def export_to_parquet(db_path: str, output_file: str):
    """Export finalized data from DuckDB to Parquet."""
    con = duckdb.connect(db_path)
    try:
        logger.info(f"Exporting data from {db_path} to {output_file}...")
        con.sql(f"COPY enriched_builds TO '{output_file}' (FORMAT PARQUET)")
        logger.info("Export complete.")
    except Exception as e:
        logger.error(f"Failed to export: {e}")
    finally:
        con.close()


def load_tokens(token_file: str) -> List[str]:
    """Load tokens from file."""
    tokens = []
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    tokens.append(line)
    logger.info(f"Loaded {len(tokens)} tokens from {token_file}")
    return tokens


def clone_repo(project_name: str, repos_dir: str) -> Optional[str]:
    """Clone a GitHub repository."""
    owner, repo = project_name.split("/")
    repo_dir = os.path.join(repos_dir, f"{owner}_{repo}")

    if os.path.exists(repo_dir):
        logger.debug(f"Repo {project_name} already exists")
        return repo_dir

    repo_url = f"https://github.com/{project_name}.git"

    try:
        logger.info(f"Cloning {project_name}...")
        subprocess.run(
            ["git", "clone", "--depth", "1000", repo_url, repo_dir],
            capture_output=True,
            timeout=300,
        )
        logger.info(f"Cloned {project_name}")
        return repo_dir
    except Exception as e:
        logger.error(f"Failed to clone {project_name}: {e}")
        return None


def cleanup_repo(repo_dir: str) -> None:
    """Delete a cloned repository."""
    try:
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup {repo_dir}: {e}")


# =============================================================================
# ENRICHMENT FUNCTIONS
# =============================================================================


def enrich_row(
    row: pd.Series,
    project_builds: pd.DataFrame,
    current_idx: int,
    client: GitHubAPIClient,
    repo_dir: Optional[str],
) -> Dict[str, Any]:
    """Enrich a single build row with new features."""
    features = {f: None for f in NEW_FEATURES}

    # Parse commit info
    git_all_built_commits = []
    if pd.notna(row.get("git_all_built_commits")):
        git_all_built_commits = str(row["git_all_built_commits"]).split("#")

    commit_date = parse_datetime(row.get("gh_build_started_at"))

    # --- SOURCE CODE STREAM ---
    if repo_dir and git_all_built_commits:
        features["change_entropy"] = extract_change_entropy(git_all_built_commits, repo_dir)
        features["file_change_frequency"] = extract_file_change_frequency(
            git_all_built_commits, repo_dir, commit_date
        )

    # Churn ratio
    current_churn = row.get("git_diff_src_churn", 0) or 0
    avg_churn = features.get("avg_src_churn_last_5", 0) or 0
    features["churn_ratio_vs_avg"] = calculate_churn_ratio_vs_avg(current_churn, avg_churn)

    # --- TEST & COVERAGE STREAM ---
    prev_features = extract_prev_build_features(None, current_idx, project_builds)
    features.update(prev_features)

    # --- TEAM ACTIVITY STREAM ---
    if row.get("gh_is_pr") and pd.notna(row.get("gh_pull_req_num")):
        pr_features = extract_pr_features(client, int(row["gh_pull_req_num"]), row.to_dict())
        features.update(pr_features)

    if repo_dir and git_all_built_commits:
        features["author_ownership"] = extract_author_ownership(
            git_all_built_commits, repo_dir, commit_date
        )
        features["is_new_contributor"] = check_is_new_contributor(
            git_all_built_commits, repo_dir, commit_date
        )

    # --- MONITORING STREAM ---
    time_features = extract_build_time_features(row.get("gh_build_started_at"))
    features.update(time_features)

    # Time since previous build
    if current_idx > 0:
        prev_row = project_builds.iloc[current_idx - 1]
        features["time_since_prev_build"] = calculate_time_since_prev_build(
            row.get("gh_build_started_at"), prev_row.get("gh_build_started_at")
        )

    # --- ADDITIONAL GIT FEATURES ---
    if repo_dir and git_all_built_commits:
        features["commit_message_length"] = extract_commit_message_length(
            git_all_built_commits, repo_dir
        )
        features["has_issue_reference"] = check_has_issue_reference(git_all_built_commits, repo_dir)
        features["days_since_last_author_commit"] = extract_days_since_last_author_commit(
            git_all_built_commits, repo_dir, commit_date
        )
        # Note: using first commit of the build as trigger/HEAD approximation for these checks
        if len(git_all_built_commits) > 0:
            features["is_merge_commit"] = check_is_merge_commit(git_all_built_commits[0], repo_dir)
        features["author_total_commits"] = extract_author_total_commits(
            git_all_built_commits, repo_dir
        )

    features["files_modified_ratio"] = calculate_files_modified_ratio(row.to_dict())

    # --- ADDITIONAL PR FEATURES ---
    if row.get("gh_is_pr") and pd.notna(row.get("gh_pull_req_num")):
        extra_pr_features = extract_pr_extra_features(
            client, int(row["gh_pull_req_num"]), row.to_dict()
        )
        features.update(extra_pr_features)

    return features


def process_project_batch(
    project_name: str,
    project_df: pd.DataFrame,
    token_manager: TokenManager,
    repos_dir: str,
    cache_dir: str,
    db_path: str,
) -> int:
    """
    Process all builds for a single project IN BATCHES.
    Saves each batch to DB immediately to reduce RAM usage.
    Returns total number of processed builds.
    """

    # Sort by build number
    project_df = project_df.sort_values("tr_build_number").reset_index(drop=True)
    total_builds = len(project_df)
    batch_size = CONFIG["batch_size"]

    # Setup client
    owner, repo = project_name.split("/")
    client = GitHubAPIClient(owner, repo, token_manager=token_manager, cache_dir=cache_dir)

    # Clone repo once for entire project
    repo_dir = clone_repo(project_name, repos_dir)

    # Process in batches
    num_batches = (total_builds + batch_size - 1) // batch_size
    logger.info(f"Processing {total_builds} builds in {num_batches} batches (size={batch_size})...")

    processed_count = 0

    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, total_builds)
        batch_df = project_df.iloc[start_idx:end_idx].copy()

        logger.info(f"  Batch {batch_idx + 1}/{num_batches}: rows {start_idx}-{end_idx}")

        enriched_features = [None] * len(batch_df)

        with ThreadPoolExecutor(max_workers=CONFIG["max_workers"]) as executor:

            def process_single_row(args):
                local_idx, global_idx, row = args
                try:
                    # Pass global index for prev_build features
                    return enrich_row(row, project_df, global_idx, client, repo_dir)
                except Exception as e:
                    logger.error(
                        f"Error enriching {project_name} build {row.get('tr_build_id')}: {e}"
                    )
                    return {f: None for f in NEW_FEATURES}

            # Submit batch tasks
            futures = {}
            for local_idx, (global_idx, row) in enumerate(batch_df.iterrows()):
                # global_idx is the index in project_df (after reset_index)
                # For batch_df from iloc, global_idx = start_idx + local_idx
                actual_global_idx = start_idx + local_idx
                futures[
                    executor.submit(process_single_row, (local_idx, actual_global_idx, row))
                ] = local_idx

            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc=f"  Batch {batch_idx + 1}",
                leave=False,
            ):
                local_idx = futures[future]
                try:
                    enriched_features[local_idx] = future.result()
                except Exception as e:
                    logger.error(f"Worker exception: {e}")
                    enriched_features[local_idx] = {f: None for f in NEW_FEATURES}

        # Create batch result and save immediately
        features_df = pd.DataFrame(enriched_features)
        batch_result = pd.concat([batch_df.reset_index(drop=True), features_df], axis=1)

        # Save batch to DB
        save_to_db(batch_result, db_path)
        processed_count += len(batch_result)

        # Free memory
        del batch_df
        del enriched_features
        del features_df
        del batch_result
        gc.collect()

    # Cleanup repo after all batches done
    if CONFIG["cleanup_repos"] and repo_dir:
        cleanup_repo(repo_dir)

    return processed_count


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Enrich builds data with GitHub features")
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output Parquet file")
    parser.add_argument("--tokens", default="tokens.txt", help="Token file")
    parser.add_argument("--repos-dir", default="repos", help="Directory for cloned repos")
    parser.add_argument("--cache-dir", default="cache", help="Cache directory")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers")
    parser.add_argument("--project", help="Process single project (for testing)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose API logging")
    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        # Set root to DEBUG to allow all debug logs through handlers
        logging.getLogger().setLevel(logging.DEBUG)
        # Silence noisy libraries
        logging.getLogger("urllib3").setLevel(logging.INFO)
        logging.getLogger("requests").setLevel(logging.INFO)
        logging.getLogger("duckdb").setLevel(logging.INFO)
        logging.getLogger("matplotlib").setLevel(logging.INFO)
    else:
        logging.getLogger().setLevel(logging.INFO)

    # Setup directories
    os.makedirs(args.repos_dir, exist_ok=True)
    os.makedirs(args.cache_dir, exist_ok=True)
    CONFIG["repos_dir"] = args.repos_dir
    CONFIG["cache_dir"] = args.cache_dir
    CONFIG["max_workers"] = args.workers

    # Load tokens
    tokens = load_tokens(args.tokens)
    if not tokens:
        logger.error("No tokens found! Create a tokens.txt file with GitHub tokens.")
        sys.exit(1)

    token_manager = TokenManager(tokens)

    # Initialize DB
    logger.info(f"Initializing DuckDB: {CONFIG['db_path']}")
    init_db(CONFIG["db_path"])

    # Get processed IDs to skip
    processed_ids = get_processed_ids(CONFIG["db_path"])
    logger.info(f"Found {len(processed_ids)} already processed builds in DB")

    # Load data
    logger.info(f"Loading data from {args.input}...")
    df = pd.read_csv(args.input)
    logger.info(f"Loaded {len(df)} rows")

    # Filter to single project if specified
    if args.project:
        df = df[df["gh_project_name"] == args.project]
        logger.info(f"Filtered to project {args.project}: {len(df)} rows")

    # Filter out processed builds
    if processed_ids:
        original_count = len(df)
        df = df[~df["tr_build_id"].isin(processed_ids)]
        logger.info(f"Skipping {original_count - len(df)} processed builds. Remaining: {len(df)}")

    if df.empty:
        logger.info("All builds already processed!")
    else:
        # Process by project
        projects = df["gh_project_name"].unique()
        logger.info(f"Processing {len(projects)} projects...")

        for project in tqdm(projects, desc="Projects"):
            try:
                project_df = df[df["gh_project_name"] == project].copy()

                # Process in batches (saves to DB internally)
                processed = process_project_batch(
                    project,
                    project_df,
                    token_manager,
                    args.repos_dir,
                    args.cache_dir,
                    CONFIG["db_path"],
                )
                logger.info(f"✅ Completed {project}: {processed} builds")

                # Free memory
                del project_df
                gc.collect()

            except Exception as e:
                logger.error(f"Failed to process {project}: {e}")

    # Export final result
    export_to_parquet(CONFIG["db_path"], args.output)


if __name__ == "__main__":
    main()
