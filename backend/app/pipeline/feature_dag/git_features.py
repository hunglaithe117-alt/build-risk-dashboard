"""
Git-related features.

Features extracted from git history and repository operations:
- Commit info (all commits in build, previous build)
- Diff statistics (churn, file counts)
- File touch history
- Team membership
"""
import re
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from hamilton.function_modifiers import extract_fields, tag

from app.pipeline.feature_dag.analyzers import (
    _count_test_cases,
    _is_doc_file,
    _is_source_file,
    _is_test_file,
)
from app.pipeline.feature_dag._inputs import (
    GitHistoryInput,
    RepoInput,
    BuildRunInput,
)
from app.pipeline.feature_dag._metadata import (
    feature_metadata,
    FeatureCategory,
    FeatureDataType,
    FeatureResource,
    OutputFormat,
)
from app.pipeline.utils.git_utils import (
    get_author_name,
    get_commit_info,
    get_commit_parents,
    get_committed_date,
    get_committer_name,
    get_diff_files,
    git_log_files,
    iter_commit_history,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Commit Info Features
# =============================================================================


@extract_fields(
    {
        "git_all_built_commits": list,
        "git_num_all_built_commits": int,
        "git_prev_built_commit": Optional[str],
        "git_prev_commit_resolution_status": str,
        "tr_prev_build": Optional[str],
    }
)
@tag(group="git")
@feature_metadata(
    display_name="Git Commit Info",
    description="Commits included in build and previous build reference",
    category=FeatureCategory.GIT_HISTORY,
    data_type=FeatureDataType.JSON,
    required_resources=[
        FeatureResource.GIT_HISTORY,
        FeatureResource.RAW_BUILD_RUNS,
        FeatureResource.BUILD_RUN,
    ],
    output_formats={
        "git_all_built_commits": OutputFormat.HASH_SEPARATED,
    },
)
def git_commit_info(
    git_history: GitHistoryInput,
    repo: RepoInput,
    build_run: BuildRunInput,
    raw_build_runs: Any,
) -> Dict[str, Any]:
    """
    Determine commits included in this build and find previous build.

    Walks commit history from HEAD until finding a previously-built commit
    or encountering a merge commit.
    """
    if not git_history.is_commit_available:
        return {
            "git_all_built_commits": [],
            "git_num_all_built_commits": 0,
            "git_prev_built_commit": None,
            "git_prev_commit_resolution_status": "commit_not_found",
            "tr_prev_build": None,
        }

    effective_sha = git_history.effective_sha
    repo_path = git_history.path

    if not effective_sha:
        return {
            "git_all_built_commits": [],
            "git_num_all_built_commits": 0,
            "git_prev_built_commit": None,
            "git_prev_commit_resolution_status": "commit_not_found",
            "tr_prev_build": None,
        }

    # Walk history to find previous build
    commits_hex: List[str] = [effective_sha]
    status = "no_previous_build"
    last_commit_sha: Optional[str] = None
    prev_build_id = None

    first = True
    for commit_info in iter_commit_history(repo_path, effective_sha, max_count=1000):
        hexsha = commit_info["hexsha"]
        parents = commit_info["parents"]

        if first:
            if len(parents) > 1:
                status = "merge_found"
                break
            first = False
            continue

        last_commit_sha = hexsha

        # Check if this commit has a build in DB
        existing_build = raw_build_runs.find_one(
            {"head_sha": hexsha, "repo_id": repo.id}
        )

        if existing_build:
            status = "build_found"
            prev_build_id = existing_build.get("workflow_run_id")
            break

        commits_hex.append(hexsha)

        if len(parents) > 1:
            status = "merge_found"
            break

    return {
        "git_all_built_commits": commits_hex,
        "git_num_all_built_commits": len(commits_hex),
        "git_prev_built_commit": last_commit_sha,
        "git_prev_commit_resolution_status": status,
        "tr_prev_build": str(prev_build_id) if prev_build_id else None,
    }


@extract_fields(
    {
        "git_diff_src_churn": int,
        "git_diff_test_churn": int,
        "gh_diff_files_added": int,
        "gh_diff_files_deleted": int,
        "gh_diff_files_modified": int,
        "gh_diff_tests_added": int,
        "gh_diff_tests_deleted": int,
        "gh_diff_src_files": int,
        "gh_diff_doc_files": int,
        "gh_diff_other_files": int,
    }
)
@tag(group="git")
def git_diff_features(
    git_history: GitHistoryInput,
    repo: RepoInput,
    git_all_built_commits: List[str],
    git_prev_built_commit: Optional[str],
) -> Dict[str, Any]:
    """Calculate diff statistics across all built commits."""
    if not git_history.is_commit_available:
        return _empty_diff_result()

    repo_path = git_history.path
    effective_sha = git_history.effective_sha

    # Normalize languages
    languages = [lang.lower() for lang in repo.source_languages] or [""]

    stats = _empty_diff_result()

    # Cumulative changes across all built commits
    for sha in git_all_built_commits:
        parent = _get_parent_commit(repo_path, sha)
        if not parent:
            continue

        # File status changes
        try:
            name_status_out = _run_git(
                repo_path, ["diff", "--name-status", parent, sha]
            )
            for line in name_status_out.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue

                status_code = parts[0][0]
                path = parts[-1]

                if status_code == "A":
                    stats["gh_diff_files_added"] += 1
                elif status_code == "D":
                    stats["gh_diff_files_deleted"] += 1
                elif status_code == "M":
                    stats["gh_diff_files_modified"] += 1

                is_test = any(_is_test_file(path, lang) for lang in languages)

                if _is_doc_file(path):
                    stats["gh_diff_doc_files"] += 1
                elif _is_source_file(path) or is_test:
                    stats["gh_diff_src_files"] += 1
                else:
                    stats["gh_diff_other_files"] += 1
        except Exception:
            continue

        # Line churn
        try:
            numstat_out = _run_git(repo_path, ["diff", "--numstat", parent, sha])
            for line in numstat_out.splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue

                try:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    deleted = int(parts[1]) if parts[1] != "-" else 0
                except ValueError:
                    continue

                path = parts[2]
                churn = added + deleted

                is_test = any(_is_test_file(path, lang) for lang in languages)

                if _is_source_file(path):
                    stats["git_diff_src_churn"] += churn
                elif is_test:
                    stats["git_diff_test_churn"] += churn
        except Exception:
            continue

    # Test case diff (prev built commit vs current)
    if git_prev_built_commit and effective_sha:
        try:
            patch_out = _run_git(
                repo_path, ["diff", git_prev_built_commit, effective_sha]
            )
            total_added = 0
            total_deleted = 0
            for lang in languages:
                added, deleted = _count_test_cases(patch_out, lang)
                total_added += added
                total_deleted += deleted

            stats["gh_diff_tests_added"] = total_added
            stats["gh_diff_tests_deleted"] = total_deleted
        except Exception:
            pass

    return stats


def _empty_diff_result() -> Dict[str, int]:
    return {
        "git_diff_src_churn": 0,
        "git_diff_test_churn": 0,
        "gh_diff_files_added": 0,
        "gh_diff_files_deleted": 0,
        "gh_diff_files_modified": 0,
        "gh_diff_tests_added": 0,
        "gh_diff_tests_deleted": 0,
        "gh_diff_src_files": 0,
        "gh_diff_doc_files": 0,
        "gh_diff_other_files": 0,
    }


def _get_parent_commit(cwd: Path, sha: str) -> Optional[str]:
    """Get parent commit SHA."""
    try:
        return _run_git(cwd, ["rev-parse", f"{sha}^"])
    except subprocess.CalledProcessError:
        return None


def _run_git(cwd: Path, args: list) -> str:
    """Run git command and return output."""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


LOOKBACK_DAYS = 90
CHUNK_SIZE = 50


@feature_metadata(
    display_name="Commits on Files Touched",
    description="Number of commits that touched files modified in this build (last 90 days)",
    category=FeatureCategory.GIT_HISTORY,
    data_type=FeatureDataType.INTEGER,
    required_resources=[FeatureResource.GIT_HISTORY, FeatureResource.BUILD_RUN],
)
@tag(group="git")
def gh_num_commits_on_files_touched(
    git_history: GitHistoryInput,
    build_run: BuildRunInput,
    git_all_built_commits: List[str],
) -> int:
    """Count commits that touched files modified in this build (last 90 days)."""
    if not git_history.is_commit_available:
        return 0

    if not git_all_built_commits:
        return 0

    repo_path = git_history.path
    effective_sha = git_history.effective_sha

    # Get reference date
    ref_date = build_run.created_at
    if not ref_date:
        committed_date = get_committed_date(repo_path, effective_sha)
        if committed_date:
            ref_date = datetime.fromtimestamp(committed_date, tz=timezone.utc)
        else:
            return 0

    if ref_date.tzinfo is None:
        ref_date = ref_date.replace(tzinfo=timezone.utc)

    start_date = ref_date - timedelta(days=LOOKBACK_DAYS)

    # Collect files touched by this build
    files_touched: Set[str] = set()
    for sha in git_all_built_commits:
        parents = get_commit_parents(repo_path, sha)
        if parents:
            diff_files = get_diff_files(repo_path, parents[0], sha)
            for f in diff_files:
                if f.get("b_path"):
                    files_touched.add(f["b_path"])
                if f.get("a_path"):
                    files_touched.add(f["a_path"])

    if not files_touched:
        return 0

    # Count commits on these files
    paths = list(files_touched)
    start_iso = start_date.isoformat()
    trigger_sha = git_all_built_commits[0] if git_all_built_commits else effective_sha

    try:
        all_shas = git_log_files(repo_path, trigger_sha, start_iso, paths, CHUNK_SIZE)
        # Exclude commits that are part of this build
        for sha in git_all_built_commits:
            all_shas.discard(sha)
        return len(all_shas)
    except Exception as e:
        logger.warning(f"Failed to count commits on files: {e}")
        return 0

@feature_metadata(
    display_name="Team Size",
    description="Number of unique contributors in last 90 days",
    category=FeatureCategory.TEAM,
    data_type=FeatureDataType.INTEGER,
    required_resources=[
        FeatureResource.GIT_HISTORY,
        FeatureResource.RAW_BUILD_RUNS,
        FeatureResource.BUILD_RUN,
    ],
)
@tag(group="git")
def gh_team_size(
    git_history: GitHistoryInput,
    build_run: BuildRunInput,
    raw_build_runs: Any,
    repo: RepoInput,
) -> int:
    """Number of unique contributors in last 90 days."""
    if not git_history.is_commit_available:
        return 0

    repo_path = git_history.path
    effective_sha = git_history.effective_sha

    if not effective_sha:
        return 0

    commit_info = get_commit_info(repo_path, effective_sha)
    committed_date = commit_info.get("committed_date")

    if not committed_date:
        return 0

    ref_date = build_run.created_at
    if not ref_date:
        ref_date = datetime.fromtimestamp(committed_date, tz=timezone.utc)
    if ref_date.tzinfo is None:
        ref_date = ref_date.replace(tzinfo=timezone.utc)

    start_date = ref_date - timedelta(days=LOOKBACK_DAYS)

    # Get direct committers (excluding PR merges)
    committer_names = _get_direct_committers(repo_path, start_date, ref_date)

    # Get PR mergers from workflow runs
    merger_logins = _get_pr_mergers(raw_build_runs, repo.id, start_date, ref_date)

    core_team = committer_names | merger_logins
    return len(core_team)


@feature_metadata(
    display_name="By Core Team Member",
    description="Whether build author is a core team member",
    category=FeatureCategory.TEAM,
    data_type=FeatureDataType.BOOLEAN,
    required_resources=[
        FeatureResource.GIT_HISTORY,
        FeatureResource.RAW_BUILD_RUNS,
        FeatureResource.BUILD_RUN,
    ],
)
@tag(group="git")
def gh_by_core_team_member(
    git_history: GitHistoryInput,
    gh_team_size: int,
    build_run: BuildRunInput,
    raw_build_runs: Any,
    repo: RepoInput,
) -> bool:
    """Whether build author is a core team member."""
    if not git_history.is_commit_available or gh_team_size == 0:
        return False

    repo_path = git_history.path
    effective_sha = git_history.effective_sha

    if not effective_sha:
        return False

    commit_info = get_commit_info(repo_path, effective_sha)
    committed_date = commit_info.get("committed_date")

    if not committed_date:
        return False

    ref_date = build_run.created_at
    if not ref_date:
        ref_date = datetime.fromtimestamp(committed_date, tz=timezone.utc)
    if ref_date.tzinfo is None:
        ref_date = ref_date.replace(tzinfo=timezone.utc)

    start_date = ref_date - timedelta(days=LOOKBACK_DAYS)

    # Get core team
    committer_names = _get_direct_committers(repo_path, start_date, ref_date)
    merger_logins = _get_pr_mergers(raw_build_runs, repo.id, start_date, ref_date)
    core_team = committer_names | merger_logins

    # Check if build author is in core team
    author_name = get_author_name(repo_path, effective_sha)
    committer_name = get_committer_name(repo_path, effective_sha)

    if author_name and author_name in core_team:
        return True
    if committer_name and committer_name in core_team:
        return True

    return False


def _get_direct_committers(
    repo_path: Path, start_date: datetime, end_date: datetime
) -> Set[str]:
    """Get names of users who pushed directly (not via PR)."""
    pr_pattern = re.compile(r"\s\(#\d+\)")

    try:
        cmd = [
            "git",
            "log",
            "--first-parent",
            "--no-merges",
            f"--since={start_date.isoformat()}",
            f"--until={end_date.isoformat()}",
            "--format=%H|%an|%s",
        ]
        result = subprocess.run(
            cmd, cwd=str(repo_path), capture_output=True, text=True, check=True
        )
        output = result.stdout.strip()
    except subprocess.CalledProcessError:
        return set()

    direct_committers = set()
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        name, message = parts[1], parts[2]
        if pr_pattern.search(message) or "Merge pull request" in message:
            continue
        direct_committers.add(name)

    return direct_committers


def _get_pr_mergers(
    raw_build_runs: Any,
    repo_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Set[str]:
    """Get logins of users who triggered PR workflow runs."""
    mergers: Set[str] = set()
    try:
        cursor = raw_build_runs.find(
            {
                "repo_id": repo_id,
                "created_at": {"$gte": start_date, "$lte": end_date},
            }
        )

        for doc in cursor:
            payload = doc.get("raw_payload", {})
            pull_requests = payload.get("pull_requests", [])
            is_pr = len(pull_requests) > 0 or payload.get("event") == "pull_request"
            if is_pr:
                actor = payload.get("triggering_actor", {})
                login = actor.get("login")
                if login:
                    mergers.add(login)
    except Exception as e:
        logger.warning(f"Failed to get PR mergers: {e}")

    return mergers
