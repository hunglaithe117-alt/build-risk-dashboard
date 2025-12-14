"""
Repository snapshot features.

Features extracted from repository state at build time:
- Repository age and commit count
- SLOC metrics
- Test density metrics
"""

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hamilton.function_modifiers import extract_fields, tag

from app.pipeline.feature_dag._inputs import (
    GitHistoryInput,
    GitWorktreeInput,
    RepoInput,
)
from app.pipeline.feature_dag._metadata import (
    feature_metadata,
    FeatureCategory,
    FeatureDataType,
    FeatureResource,
)
from app.pipeline.feature_dag.languages import LanguageRegistry

logger = logging.getLogger(__name__)


@feature_metadata(
    display_name="Repository Age",
    description="Repository age in days (from first commit to build commit)",
    category=FeatureCategory.REPO_SNAPSHOT,
    data_type=FeatureDataType.FLOAT,
    required_resources=[FeatureResource.GIT_HISTORY],
    unit="days",
)
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

        latest_commit_date = datetime.fromtimestamp(
            int(latest_commit_ts), tz=timezone.utc
        )
        first_commit_date = datetime.fromtimestamp(
            int(first_commit_ts), tz=timezone.utc
        )

        # Age = time from first commit to build commit
        age_days = (latest_commit_date - first_commit_date).days
        return float(age_days)
    except Exception as e:
        logger.warning(f"Failed to get repo age: {e}")
        return None


@feature_metadata(
    display_name="Total Commits",
    description="Total number of commits in repository history",
    category=FeatureCategory.REPO_SNAPSHOT,
    data_type=FeatureDataType.INTEGER,
    required_resources=[FeatureResource.GIT_HISTORY],
)
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
        "gh_asserts_case_per_kloc": Optional[float],
    }
)
@feature_metadata(
    display_name="Code Metrics",
    description="SLOC and test density metrics",
    category=FeatureCategory.REPO_SNAPSHOT,
    data_type=FeatureDataType.JSON,
    required_resources=[FeatureResource.GIT_WORKTREE, FeatureResource.REPO],
)
@tag(group="repo")
def repo_code_metrics(
    git_worktree: GitWorktreeInput,
    repo: RepoInput,
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
            "gh_asserts_case_per_kloc": None,
        }

    worktree_path = git_worktree.worktree_path
    languages = [lang.lower() for lang in repo.source_languages] or [""]

    src_lines, test_lines, test_cases, asserts = _count_code_metrics(
        worktree_path, languages
    )

    metrics = {
        "gh_sloc": src_lines,
        "gh_test_lines_per_kloc": None,
        "gh_test_cases_per_kloc": None,
        "gh_asserts_case_per_kloc": None,
    }

    if src_lines > 0:
        kloc = src_lines / 1000.0
        metrics["gh_test_lines_per_kloc"] = test_lines / kloc
        metrics["gh_test_cases_per_kloc"] = test_cases / kloc
        metrics["gh_asserts_case_per_kloc"] = asserts / kloc

    return metrics


def _count_code_metrics(
    worktree_path: Path, languages: List[str]
) -> Tuple[int, int, int, int]:
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
