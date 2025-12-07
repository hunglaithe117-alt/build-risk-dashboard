"""
Git Diff Features Node.

Extracts diff-related metrics:
- Source/test churn
- File counts by type
- Test case changes
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle
from app.pipeline.analyzers import (
    _count_test_cases,
    _is_doc_file,
    _is_source_file,
    _is_test_file,
)

logger = logging.getLogger(__name__)


@register_feature(
    name="git_diff_features",
    requires_resources={ResourceNames.GIT_REPO},
    requires_features={"git_all_built_commits", "git_prev_built_commit"},
    provides={
        "git_diff_src_churn",
        "git_diff_test_churn",
        "gh_diff_files_added",
        "gh_diff_files_deleted",
        "gh_diff_files_modified",
        "gh_diff_tests_added",
        "gh_diff_tests_deleted",
        "gh_diff_src_files",
        "gh_diff_doc_files",
        "gh_diff_other_files",
    },
    group="git",
)
class GitDiffFeaturesNode(FeatureNode):
    """
    Calculates diff statistics for the build.

    Computes:
    - Cumulative churn across all built commits
    - File counts by category (source, doc, other)
    - Test case additions/deletions
    """

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        git_handle: GitRepoHandle = context.get_resource(ResourceNames.GIT_REPO)
        repo = context.repo

        if not git_handle.is_commit_available:
            return self._empty_result()

        built_commits = context.get_feature("git_all_built_commits", [])
        prev_built_commit = context.get_feature("git_prev_built_commit")

        # Get primary language for test detection
        # Get all source languages for test detection
        languages = []
        if repo.source_languages:
            for lang in repo.source_languages:
                val = (
                    lang.value.lower() if hasattr(lang, "value") else str(lang).lower()
                )
                languages.append(val)

        stats = self._calculate_diff_stats(
            git_handle.path,
            built_commits,
            prev_built_commit,
            git_handle.effective_sha,
            languages,
        )

        return stats

    def _calculate_diff_stats(
        self,
        cwd: Path,
        built_commits: List[str],
        prev_built_commit: str | None,
        current_commit: str,
        languages: List[str],
    ) -> Dict[str, Any]:
        """Calculate all diff statistics."""
        stats = self._empty_result()

        # Normalize languages
        langs = [(l or "").lower() for l in (languages or [])]
        if not langs:
            langs = [""]

        # 1. Cumulative changes across all built commits
        for sha in built_commits:
            parent = self._get_parent_commit(cwd, sha)
            if not parent:
                continue

            # File status changes
            try:
                name_status_out = self._run_git(
                    cwd, ["diff", "--name-status", parent, sha]
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

                    is_test = False
                    for lang in langs:
                        if _is_test_file(path, lang):
                            is_test = True
                            break

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
                numstat_out = self._run_git(cwd, ["diff", "--numstat", parent, sha])
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

                    is_test = False
                    for lang in langs:
                        if _is_test_file(path, lang):
                            is_test = True
                            break

                    if _is_source_file(path):
                        stats["git_diff_src_churn"] += churn
                    elif is_test:
                        stats["git_diff_test_churn"] += churn
            except Exception:
                continue

        # 2. Test case diff (prev built commit vs current)
        if prev_built_commit:
            try:
                patch_out = self._run_git(
                    cwd, ["diff", prev_built_commit, current_commit]
                )

                total_added = 0
                total_deleted = 0
                for lang in langs:
                    added, deleted = _count_test_cases(patch_out, lang)
                    total_added += added
                    total_deleted += deleted

                stats["gh_diff_tests_added"] = total_added
                stats["gh_diff_tests_deleted"] = total_deleted
            except Exception:
                pass

        return stats

    def _get_parent_commit(self, cwd: Path, sha: str) -> str | None:
        """Get parent commit SHA."""
        try:
            return self._run_git(cwd, ["rev-parse", f"{sha}^"])
        except subprocess.CalledProcessError:
            return None

    def _run_git(self, cwd: Path, args: list) -> str:
        """Run git command and return output."""
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _empty_result(self) -> Dict[str, Any]:
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
