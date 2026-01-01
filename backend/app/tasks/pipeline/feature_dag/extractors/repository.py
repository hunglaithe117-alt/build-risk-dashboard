"""
Repository and GitHub API features.

Features extracted from repository state and GitHub API:
- Repository age and commit count
- SLOC metrics, Test density
- PR/Issue comments, Labels
"""

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hamilton.function_modifiers import extract_fields, tag

from app.tasks.pipeline.feature_dag._inputs import (
    BuildRunInput,
    GitHistoryInput,
    GitHubClientInput,
    GitWorktreeInput,
    RawBuildRunsCollection,
    RepoInput,
)
from app.tasks.pipeline.feature_dag._retry import with_retry
from app.tasks.pipeline.feature_dag.languages import LanguageRegistry
from app.utils.datetime import ensure_naive_utc

logger = logging.getLogger(__name__)


@tag(group="repo")
def gh_repo_age(git_history: GitHistoryInput) -> Optional[float]:
    """
    Repository age in days.
    """
    if not git_history.is_commit_available or not git_history.effective_sha:
        return None

    repo_path = git_history.path
    sha = git_history.effective_sha

    try:
        # Get timestamp of the build trigger commit
        latest_commit_ts = subprocess.run(
            ["git", "log", "-1", "--format=%ct", sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Get timestamp of the first commit in the repo (reachable from sha)
        first_commit_ts = (
            subprocess.run(
                ["git", "log", "--reverse", "--format=%ct", sha],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .split("\n")[0]
        )

        latest_commit_date = datetime.fromtimestamp(int(latest_commit_ts), tz=timezone.utc)
        first_commit_date = datetime.fromtimestamp(int(first_commit_ts), tz=timezone.utc)

        # Age = time from first commit to build commit
        age_days = (latest_commit_date - first_commit_date).days
        return float(age_days)
    except Exception as e:
        logger.warning(f"Failed to get repo age: {e}")
        return None


@tag(group="repo")
def gh_repo_num_commits(git_history: GitHistoryInput) -> Optional[int]:
    """Total number of commits in repository history."""
    if not git_history.is_commit_available or not git_history.effective_sha:
        return None

    repo_path = git_history.path
    sha = git_history.effective_sha

    try:
        commit_count = subprocess.run(
            ["git", "rev-list", "--count", sha],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return int(commit_count)
    except Exception as e:
        logger.warning(f"Failed to get commit count: {e}")
        return None


@extract_fields(
    {
        "gh_sloc": Optional[int],
        "gh_test_lines_per_kloc": Optional[float],
        "gh_test_cases_per_kloc": Optional[float],
        "gh_asserts_cases_per_kloc": Optional[float],
    }
)
@tag(group="repo")
def repo_code_metrics(
    git_worktree: GitWorktreeInput,
    tr_log_lan_all: List[str],
) -> Dict[str, Any]:
    """
    SLOC and test density metrics.

    Requires a git worktree to analyze source files.
    """
    if not git_worktree.is_ready or not git_worktree.worktree_path:
        return {
            "gh_sloc": None,
            "gh_test_lines_per_kloc": None,
            "gh_test_cases_per_kloc": None,
            "gh_asserts_cases_per_kloc": None,
        }

    worktree_path = git_worktree.worktree_path
    languages = tr_log_lan_all

    src_lines, test_lines, test_cases, asserts = _count_code_metrics(worktree_path, languages)

    metrics = {
        "gh_sloc": src_lines,
        "gh_test_lines_per_kloc": None,
        "gh_test_cases_per_kloc": None,
        "gh_asserts_cases_per_kloc": None,
    }

    if src_lines > 0:
        kloc = src_lines / 1000.0
        metrics["gh_test_lines_per_kloc"] = test_lines / kloc
        metrics["gh_test_cases_per_kloc"] = test_cases / kloc
        metrics["gh_asserts_cases_per_kloc"] = asserts / kloc

    return metrics


def _count_code_metrics(worktree_path: Path, languages: List[str]) -> Tuple[int, int, int, int]:
    """
    Count source lines, test lines, test cases, and assertions.

    Returns:
        Tuple of (src_lines, test_lines, test_cases, asserts)
    """
    src_lines = 0
    test_lines = 0
    test_cases = 0
    asserts = 0

    langs_to_check = languages if languages else [None]

    for path in worktree_path.rglob("*"):
        if not path.is_file():
            continue

        rel_path = str(path.relative_to(worktree_path))

        # Skip hidden and vendor directories
        if any(part.startswith(".") for part in rel_path.split("/")):
            continue
        if any(x in rel_path for x in ["vendor/", "node_modules/", "venv/"]):
            continue

        try:
            content = path.read_text(errors="ignore")
            lines = content.splitlines()
            line_count = len(lines)

            matched_strategy = None
            is_test = False

            for lang_name in langs_to_check:
                strategy = LanguageRegistry.get_strategy(lang_name or "")
                if strategy.is_test_file(rel_path):
                    is_test = True
                    matched_strategy = strategy
                    break

            if is_test and matched_strategy:
                test_lines += line_count
                for line in lines:
                    clean_line = matched_strategy.strip_comments(line)
                    if matched_strategy.matches_test_definition(clean_line):
                        test_cases += 1
                    if matched_strategy.matches_assertion(clean_line):
                        asserts += 1
            else:
                for lang_name in langs_to_check:
                    strategy = LanguageRegistry.get_strategy(lang_name or "")
                    if strategy.is_source_file(rel_path):
                        src_lines += line_count
                        break
        except Exception:
            continue

    return src_lines, test_lines, test_cases, asserts


@extract_fields(
    {
        "gh_num_issue_comments": int,
        "gh_num_commit_comments": int,
        "gh_num_pr_comments": int,
        "gh_description_complexity": Optional[int],
    }
)
@tag(group="github")
@with_retry(max_attempts=3)
def github_discussion_features(
    github_client: GitHubClientInput,
    repo: RepoInput,
    build_run: BuildRunInput,
    git_all_built_commits: List[str],
    raw_build_runs: RawBuildRunsCollection,
    gh_pull_req_num: Optional[int],
    gh_pr_created_at: Optional[str],
) -> Dict[str, Any]:
    client = github_client.client
    full_name = github_client.full_name

    # Get commit list
    commits_to_check = git_all_built_commits
    if not commits_to_check:
        head_sha = build_run.commit_sha
        commits_to_check = [head_sha] if head_sha else []

    # Build timestamps
    build_start_time = build_run.created_at

    # Find previous build time for PR comment window
    prev_build_start_time = _get_previous_build_start_time(
        raw_build_runs, repo.id, build_run.ci_run_id, build_start_time
    )

    # 1. Commit comments (same as before - no time filter needed)
    num_commit_comments = 0
    for sha in commits_to_check:
        try:
            comments = client.list_commit_comments(full_name, sha)
            num_commit_comments += len(comments)
        except Exception as e:
            logger.warning(f"Failed to fetch comments for commit {sha}: {e}")

    # 2. PR-specific: Issue comments on the PR + code review comments
    num_issue_comments = 0
    num_pr_comments = 0
    description_complexity = None

    # Use pr_number and pr_created_at from Hamilton DAG
    pr_number = gh_pull_req_num
    pr_created_at: Optional[datetime] = None
    if gh_pr_created_at:
        try:
            pr_created_at = datetime.fromisoformat(gh_pr_created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    if pr_number:
        try:
            # Fetch PR details for description complexity
            pr_details = client.get_pull_request(full_name, pr_number)

            # Description complexity
            title = pr_details.get("title", "") or ""
            body = pr_details.get("body", "") or ""
            description_complexity = len(title.split()) + len(body.split())

            # gh_num_issue_comments: Discussion comments on THIS PR
            num_issue_comments = _count_pr_issue_comments(
                client,
                full_name,
                pr_number,
                from_time=pr_created_at,
                to_time=build_start_time,
            )

            # gh_num_pr_comments: Code review comments on THIS PR
            num_pr_comments = _count_pr_review_comments(
                client,
                full_name,
                pr_number,
                from_time=prev_build_start_time or pr_created_at,
                to_time=build_start_time,
            )
        except Exception as e:
            logger.warning(f"Failed to fetch PR data for #{pr_number}: {e}")

    return {
        "gh_num_issue_comments": num_issue_comments,
        "gh_num_commit_comments": num_commit_comments,
        "gh_num_pr_comments": num_pr_comments,
        "gh_description_complexity": description_complexity,
    }


def _get_previous_build_start_time(
    raw_build_runs: RawBuildRunsCollection,
    repo_id: str,
    current_ci_run_id: str,
    current_build_time: Optional[datetime],
) -> Optional[datetime]:
    """Get the start time of the previous build for this repo."""
    from bson import ObjectId

    if not current_build_time:
        return None

    try:
        prev_build = raw_build_runs.find_one(
            {
                "raw_repo_id": ObjectId(repo_id),
                "created_at": {"$lt": current_build_time},
                "ci_run_id": {"$ne": current_ci_run_id},
            },
            sort=[("created_at", -1)],
        )
        if prev_build:
            return prev_build.get("created_at")
    except Exception as e:
        logger.warning(f"Failed to get previous build: {e}")
    return None


def _count_pr_issue_comments(
    client: Any,
    full_name: str,
    pr_number: int,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> int:
    """
    Count discussion comments on a specific PR within time range.

    TravisTorrent logic (line 903-919):
    - Query issue_comments where issue matches the PR
    - Filter by time: from PR creation to build start
    """
    try:
        # GitHub treats PRs as issues for comments
        comments = client.list_issue_comments(full_name, pr_number)

        # Normalize datetimes to naive UTC for comparison
        from_naive = ensure_naive_utc(from_time)
        to_naive = ensure_naive_utc(to_time)

        count = 0
        for comment in comments:
            created_at_str = comment.get("created_at", "")
            if not created_at_str:
                continue

            # Parse and convert to naive UTC
            comment_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            comment_time_naive = comment_time.replace(tzinfo=None)

            # Apply time filter
            if from_naive and comment_time_naive < from_naive:
                continue
            if to_naive and comment_time_naive > to_naive:
                continue

            count += 1

        return count
    except Exception as e:
        logger.warning(f"Failed to count PR issue comments: {e}")
        return 0


def _count_pr_review_comments(
    client: Any,
    full_name: str,
    pr_number: int,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> int:
    """
    Count code review comments on a specific PR within time range.

    TravisTorrent logic (line 886-899):
    - Query pull_request_comments
    - Filter by time: from prev_build_started_at to current build_started_at
    """
    try:
        comments = client.list_review_comments(full_name, pr_number)

        # Normalize datetimes to naive UTC for comparison
        from_naive = ensure_naive_utc(from_time)
        to_naive = ensure_naive_utc(to_time)

        count = 0
        for comment in comments:
            created_at_str = comment.get("created_at", "")
            if not created_at_str:
                continue

            # Parse and convert to naive UTC
            comment_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            comment_time_naive = comment_time.replace(tzinfo=None)

            # Apply time filter
            if from_naive and comment_time_naive < from_naive:
                continue
            if to_naive and comment_time_naive > to_naive:
                continue

            count += 1

        return count
    except Exception as e:
        logger.warning(f"Failed to count PR review comments: {e}")
        return 0


@extract_fields(
    {
        "gh_has_bug_label": Optional[bool],
    }
)
@tag(group="github")
@with_retry(max_attempts=3)
def gh_has_bug_label_feature(
    gh_pull_req_num: Optional[int],
    github_client: GitHubClientInput,
) -> Dict[str, Any]:
    """
    Check if PR has bug-related labels.
    Matches feature_extractors.py::extract_pr_features - checks for "bug" or "fix" in labels

    Uses gh_pull_req_num from build_features.py as input.
    """
    result = {"gh_has_bug_label": False}

    if not gh_pull_req_num:
        return result

    try:
        full_name = github_client.full_name
        pr_details = github_client.client.get_pull_request(full_name, gh_pull_req_num)

        # Labels can be list of dicts with "name" key
        labels = pr_details.get("labels", [])
        label_names = [lbl.get("name", "") if isinstance(lbl, dict) else str(lbl) for lbl in labels]

        result["gh_has_bug_label"] = any(
            "bug" in label.lower() or "fix" in label.lower() for label in label_names
        )
    except Exception as e:
        logger.warning(f"Failed to fetch PR #{gh_pull_req_num} labels: {e}")

    return result
