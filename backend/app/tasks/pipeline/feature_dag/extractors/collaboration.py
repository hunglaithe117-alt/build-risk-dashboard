import collections
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from hamilton.function_modifiers import extract_fields, tag

from app.tasks.pipeline.feature_dag._inputs import (
    BuildRunInput,
    FeatureVectorsCollection,
    GitHistoryInput,
    RawBuildRunsCollection,
    RepoInput,
)
from app.tasks.pipeline.utils.git_utils import (
    get_files_in_commit,
    run_git,
)

logger = logging.getLogger(__name__)


def _calculate_shannon_entropy(file_changes: List[int]) -> float:
    """
    Calculate Shannon entropy of changes across files.
    Matches: risk_features_enrichment.py::calculate_entropy
    """
    total_changes = sum(file_changes)
    if total_changes == 0:
        return 0.0

    entropy = 0.0
    for change in file_changes:
        if change > 0:
            p = change / total_changes
            entropy -= p * math.log2(p)
    return entropy


@extract_fields(
    {
        "is_prev_failed": Optional[bool],
        "prev_fail_streak": Optional[int],
        "fail_rate_last_10": Optional[float],
        "avg_src_churn_last_5": Optional[float],
    }
)
@tag(group="risk_temporal")
def prev_build_history_features(
    raw_build_runs: RawBuildRunsCollection,
    feature_vectors: FeatureVectorsCollection,
    repo: RepoInput,
    tr_prev_build: Optional[str],
) -> Dict[str, Any]:
    """
    Extract temporal features from previous builds based on LINEAR commit history.

    Uses tr_prev_build (from git_commit_info) to correctly identify the previous
    build in the commit lineage, not just chronologically.

    - is_prev_failed: True if last build (by commit lineage) failed
    - prev_fail_streak: Count of consecutive failed builds following commit chain
    - fail_rate_last_10: Failure rate in last 10 builds (by commit chain)
    - avg_src_churn_last_5: Average git_diff_src_churn from last 5 builds (by commit chain)
    """
    from bson import ObjectId

    result = {
        "is_prev_failed": None,
        "prev_fail_streak": 0,
        "fail_rate_last_10": 0.0,
        "avg_src_churn_last_5": 0.0,
    }

    if not tr_prev_build:
        return result

    try:
        # Walk backward through build chain using tr_prev_build links
        prev_builds = []
        current_build_id = tr_prev_build
        max_lookback = 20

        while current_build_id and len(prev_builds) < max_lookback:
            build_doc = raw_build_runs.find_one(
                {
                    "raw_repo_id": ObjectId(repo.id),
                    "ci_run_id": current_build_id,
                }
            )

            if not build_doc:
                break

            prev_builds.append(build_doc)

            # Get next previous build from feature_vectors (which has tr_prev_build)
            feature_doc = feature_vectors.find_one(
                {
                    "raw_repo_id": ObjectId(repo.id),
                    "raw_build_run_id": build_doc.get("_id"),
                }
            )

            # Use dedicated tr_prev_build field (or fallback to features dict)
            if feature_doc:
                next_build_id = feature_doc.get("tr_prev_build") or feature_doc.get("features", {}).get("tr_prev_build")
                if next_build_id:
                    current_build_id = next_build_id
                else:
                    break
            else:
                break

        if not prev_builds:
            return result

        # 1. is_prev_failed - check last build's conclusion
        last_build = prev_builds[0]
        last_conclusion = last_build.get("conclusion")
        if last_conclusion:
            if hasattr(last_conclusion, "value"):
                last_conclusion = last_conclusion.value
            result["is_prev_failed"] = str(last_conclusion).lower() == "failure"

        # 2. prev_fail_streak - count consecutive failures
        streak = 0
        for b in prev_builds:
            conclusion = b.get("conclusion")
            if conclusion:
                if hasattr(conclusion, "value"):
                    conclusion = conclusion.value
                if str(conclusion).lower() == "failure":
                    streak += 1
                else:
                    break
            else:
                break
        result["prev_fail_streak"] = streak

        # 3. fail_rate_last_10 - failure rate in last 10 builds
        last_10 = prev_builds[:10]
        if last_10:
            fail_count = 0
            for b in last_10:
                conclusion = b.get("conclusion")
                if conclusion:
                    if hasattr(conclusion, "value"):
                        conclusion = conclusion.value
                    if str(conclusion).lower() == "failure":
                        fail_count += 1
            result["fail_rate_last_10"] = round(fail_count / len(last_10), 4)

        # 4. avg_src_churn_last_5 - average src churn from feature_vectors
        # Use the same chain-based approach
        prev_feature_vectors = []
        for build_doc in prev_builds[:5]:
            feature_doc = feature_vectors.find_one(
                {
                    "raw_repo_id": ObjectId(repo.id),
                    "raw_build_run_id": build_doc.get("_id"),
                    "extraction_status": "completed",
                }
            )
            if feature_doc:
                prev_feature_vectors.append(feature_doc)

        if prev_feature_vectors:
            src_churns = []
            for fv in prev_feature_vectors:
                features = fv.get("features", {})
                if "git_diff_src_churn" in features:
                    churn_val = features["git_diff_src_churn"]
                    if churn_val is not None:
                        src_churns.append(churn_val)

            if src_churns:
                result["avg_src_churn_last_5"] = round(sum(src_churns) / len(src_churns), 2)

    except Exception as e:
        logger.warning(f"Failed to calculate prev build history features: {e}")

    return result


@tag(group="risk_churn")
def churn_ratio_vs_avg(
    git_diff_src_churn: int,
    avg_src_churn_last_5: Optional[float],
) -> float:
    """
    Compare current churn vs average of last 5 builds.
    Matches feature_extractors.py::calculate_churn_ratio_vs_avg

    Formula: current_churn / (avg_churn + 1)
    The +1 prevents division by zero when avg is 0.
    """
    avg = avg_src_churn_last_5 if avg_src_churn_last_5 is not None else 0.0
    return round(git_diff_src_churn / (avg + 1), 4)


@extract_fields(
    {
        "change_entropy": Optional[float],
        "files_modified_ratio": Optional[float],
    }
)
@tag(group="risk_entropy")
def change_entropy_features(
    gh_diff_files_modified: int,
    gh_diff_files_added: int,
    gh_diff_files_deleted: int,
    git_history: GitHistoryInput,
    git_all_built_commits: List[str],
) -> Dict[str, Any]:
    """
    Calculate entropy-based features.

    change_entropy: Shannon entropy of changes across files.
    - Uses 'git show -m --name-only --format=' to get modified files for each commit
    - Counts occurrences of each file
    - Calculates Shannon entropy on the distribution
    """
    result = {
        "change_entropy": 0.0,
        "files_modified_ratio": 0.0,
    }

    # files_modified_ratio
    total_files = gh_diff_files_modified + gh_diff_files_added + gh_diff_files_deleted
    if total_files > 0:
        result["files_modified_ratio"] = round(gh_diff_files_modified / total_files, 4)

    # change_entropy
    if not git_history.is_commit_available:
        return result

    repo_path = git_history.path
    file_counts = collections.Counter()

    try:
        for sha in git_all_built_commits:
            # git show -m --name-only --format= SHA
            output = run_git(repo_path, ["show", "-m", "--name-only", "--format=", sha])
            if output:
                for line in output.splitlines():
                    if line.strip():
                        file_counts[line.strip()] += 1

        if file_counts:
            result["change_entropy"] = round(
                _calculate_shannon_entropy(list(file_counts.values())), 4
            )

    except Exception as e:
        logger.warning(f"Failed to calculate change entropy: {e}")

    return result


@extract_fields(
    {
        "is_new_contributor": Optional[bool],
        "author_ownership": Optional[float],
        "days_since_last_author_commit": Optional[float],
    }
)
@tag(group="risk_author")
def author_experience_features(
    git_history: GitHistoryInput,
    build_run: BuildRunInput,
    git_all_built_commits: List[str],
) -> Dict[str, Any]:
    """
    Calculate author-based features matching original enrich features.
    Optimized: combines author collection and is_new_contributor check in one loop.

    - is_new_contributor: True if any author's first commit was < 90 days ago
    - author_ownership: % of commits on touched files by build authors
    - days_since_last_author_commit: Days since trigger author's previous commit
    """
    result = {
        "is_new_contributor": None,
        "author_ownership": 0.0,
        "days_since_last_author_commit": None,
    }

    if not git_history.is_commit_available:
        return result

    repo_path = git_history.path
    if not git_all_built_commits:
        return result

    try:
        # Optimized: Single loop to collect authors, files, and check is_new_contributor
        build_authors: set = set()
        author_emails: set = set()
        touched_files: set = set()
        is_new = False
        first_commit_sha = git_all_built_commits[0]
        trigger_email = None

        # Normalize build_run.created_at once
        current_date = build_run.created_at
        if current_date and current_date.tzinfo:
            current_date = current_date.replace(tzinfo=None)

        for idx, sha in enumerate(git_all_built_commits):
            # Get author name AND email in one git command
            author_info = run_git(repo_path, ["show", "--format=%an|%ae", "-s", sha])
            if author_info:
                parts = author_info.strip().split("|")
                if len(parts) == 2:
                    auth_name, auth_email = parts[0], parts[1]
                    build_authors.add(auth_name)

                    # Store trigger email (first commit's author)
                    if idx == 0:
                        trigger_email = auth_email

                    # Check is_new_contributor (only if not already found)
                    if not is_new and auth_email not in author_emails and current_date:
                        author_emails.add(auth_email)
                        first_commit_ts_str = run_git(
                            repo_path,
                            [
                                "log",
                                "--author=" + auth_email,
                                "--reverse",
                                "--format=%ct",
                                "-n",
                                "1",
                            ],
                        )
                        if first_commit_ts_str:
                            try:
                                first_commit_ts = int(first_commit_ts_str.strip())
                                first_commit_date = datetime.fromtimestamp(first_commit_ts, tz=None)
                                days_since = (current_date - first_commit_date).days
                                if 0 <= days_since < 90:
                                    is_new = True
                            except Exception:
                                pass

            # Get files touched
            files = get_files_in_commit(repo_path, sha)
            touched_files.update(files)

        result["is_new_contributor"] = is_new

        # 2. author_ownership - unchanged logic
        if touched_files and build_authors:
            total_commits = 0
            owned_commits = 0

            since_arg = []
            if build_run.created_at:
                since_date = build_run.created_at - timedelta(days=90)
                since_arg = [
                    f"--since={since_date.isoformat()}",
                    f"--until={build_run.created_at.isoformat()}",
                ]

            for filename in touched_files:
                if since_arg:
                    cmd = ["log"] + since_arg + ["--format=%an", "--", filename]
                else:
                    cmd = ["log", "-n", "50", "--format=%an", "--", filename]

                output = run_git(repo_path, cmd)
                if output:
                    for line in output.splitlines():
                        total_commits += 1
                        if line.strip() in build_authors:
                            owned_commits += 1

            if total_commits > 0:
                result["author_ownership"] = round(owned_commits / total_commits, 4)

        # 3. days_since_last_author_commit - use cached trigger_email
        if trigger_email and current_date:
            prev_commit_output = run_git(
                repo_path,
                ["log", "--author=" + trigger_email, "-2", "--format=%ct", first_commit_sha],
            )

            if prev_commit_output:
                lines = prev_commit_output.strip().split("\n")
                if len(lines) >= 2:
                    try:
                        prev_ts = int(lines[1])
                        prev_date = datetime.fromtimestamp(prev_ts, tz=None)
                        diff_days = (current_date - prev_date).days
                        result["days_since_last_author_commit"] = max(0.0, float(diff_days))
                    except Exception:
                        pass

    except Exception as e:
        logger.warning(f"Failed to calculate author features: {e}")

    return result


@extract_fields(
    {
        "build_time_sin": Optional[float],
        "build_time_cos": Optional[float],
        "build_hour_risk_score": Optional[float],
    }
)
@tag(group="risk_time")
def build_time_risk_features(
    build_run: BuildRunInput,
) -> Dict[str, Any]:
    """
    Calculate time-based risk features.
    build_time_sin/cos: Cyclic encoding of hour of day.
    build_hour_risk_score:
    - 1.0: Night (0-5h) - Fatigue
    - 0.9: Friday afternoon (after 16h)
    - 0.8: Weekend
    - 0.1: Normal hours
    """
    import math

    result = {
        "build_time_sin": 0.0,
        "build_time_cos": 1.0,
        "build_hour_risk_score": 0.1,  # Default to normal hours
    }

    if not build_run.created_at:
        return result

    try:
        hour = build_run.created_at.hour
        day_of_week = build_run.created_at.weekday()  # 0=Monday, 6=Sunday

        # Cyclic encoding
        result["build_time_sin"] = round(math.sin(2 * math.pi * hour / 24), 4)
        result["build_time_cos"] = round(math.cos(2 * math.pi * hour / 24), 4)

        # Risk score based on time (matching original exactly)
        if 0 <= hour < 5:
            risk = 1.0  # Night - Fatigue
        elif day_of_week == 4 and hour >= 16:  # Friday afternoon
            risk = 0.9
        elif day_of_week >= 5:  # Weekend
            risk = 0.8
        else:
            risk = 0.1  # Normal hours

        result["build_hour_risk_score"] = risk

    except Exception:
        pass

    return result
