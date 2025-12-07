"""Utilities for translating GitHub compare payloads into feature metrics."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple
from app.services.extracts.languages.registry import LanguageRegistry


DOC_PREFIXES = ("docs/", "doc/", "documentation/")
DOC_EXTENSIONS = (".md", ".rst", ".adoc", ".txt")


def _strip_comments(line: str, language: str) -> str:
    """Strip comments from a line based on language."""
    strategy = LanguageRegistry.get_strategy(language)
    return strategy.strip_comments(line)


def _is_doc_file(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith(DOC_PREFIXES) or lowered.endswith(DOC_EXTENSIONS)


def _is_test_file(path: str, language: str | None = None) -> bool:
    """
    Determine if a file is a test file based on language-specific heuristics.
    Matches TravisTorrent logic.
    """
    lang = (language or "").lower()
    strategy = LanguageRegistry.get_strategy(lang)
    return strategy.is_test_file(path)


def _is_source_file(path: str) -> bool:
    lowered = path.lower()
    if _is_doc_file(lowered) or _is_test_file(
        path
    ):  # Changed lowered to path for _is_test_file
        return False
    return lowered.endswith((".py", ".pyi", ".rb", ".rake", ".erb"))


def _count_test_cases(patch: str | None, language: str | None) -> Tuple[int, int]:
    if not patch:
        return (0, 0)
    added = deleted = 0
    lang = (language or "").lower()

    # Strategy for the specific language
    strategy = LanguageRegistry.get_strategy(lang)

    for line in patch.splitlines():
        # Strip the diff prefix
        if line.startswith("+"):
            clean_line = strategy.strip_comments(line[1:])
            if strategy.matches_test_definition(clean_line):
                added += 1
        elif line.startswith("-"):
            clean_line = strategy.strip_comments(line[1:])
            if strategy.matches_test_definition(clean_line):
                deleted += 1
    return added, deleted


def _matches_test_definition(line: str, language: str) -> bool:
    strategy = LanguageRegistry.get_strategy(language)
    return strategy.matches_test_definition(line)


def _matches_assertion(line: str, language: str) -> bool:
    strategy = LanguageRegistry.get_strategy(language)
    return strategy.matches_assertion(line)


def analyze_diff(
    files: List[Dict[str, object]], languages: List[str]
) -> Dict[str, int | float]:
    stats = {
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

    # Normalize languages
    langs = [(l or "").lower() for l in (languages or [])]
    if not langs:
        langs = [""]

    for file in files or []:
        path = file.get("filename", "")
        additions = file.get("additions", 0) or 0
        deletions = file.get("deletions", 0) or 0
        status = (file.get("status") or "").lower()
        patch = file.get("patch")

        if status == "added":
            stats["gh_diff_files_added"] += 1
        elif status == "removed":
            stats["gh_diff_files_deleted"] += 1
        else:
            stats["gh_diff_files_modified"] += 1

        classification = "other"
        matched_lang = ""

        if _is_doc_file(path):
            stats["gh_diff_doc_files"] += 1
            classification = "doc"
        else:
            # Check against all languages for test file
            for lang in langs:
                if _is_test_file(path, lang):
                    stats["git_diff_test_churn"] += additions + deletions
                    classification = "test"
                    matched_lang = lang
                    break

            if classification != "test":
                if _is_source_file(path):
                    stats["gh_diff_src_files"] += 1
                    stats["git_diff_src_churn"] += additions + deletions
                    classification = "src"
                else:
                    stats["gh_diff_other_files"] += 1

        if classification == "test":
            added_tests, deleted_tests = _count_test_cases(patch, matched_lang)
            stats["gh_diff_tests_added"] += added_tests
            stats["gh_diff_tests_deleted"] += deleted_tests

    return stats
