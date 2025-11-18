"""Utilities for translating GitHub compare payloads into feature metrics."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple


DOC_PREFIXES = ("docs/", "doc/", "documentation/")
DOC_EXTENSIONS = (".md", ".rst", ".adoc", ".txt")
TEST_DIR_HINTS = ("tests/", "test/", "spec/")


def _is_doc_file(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith(DOC_PREFIXES) or lowered.endswith(DOC_EXTENSIONS)


def _is_test_file(path: str) -> bool:
    lowered = path.lower()
    if any(hint in lowered for hint in TEST_DIR_HINTS):
        return True
    return lowered.endswith(("_test.py", "_test.rb", "test.py", "test.rb", "_spec.rb"))


def _is_source_file(path: str) -> bool:
    lowered = path.lower()
    if _is_doc_file(lowered) or _is_test_file(lowered):
        return False
    return lowered.endswith((".py", ".pyi", ".rb", ".rake", ".erb"))


def _count_test_cases(patch: str | None, language: str | None) -> Tuple[int, int]:
    if not patch:
        return (0, 0)
    added = deleted = 0
    lang = (language or "").lower()
    for line in patch.splitlines():
        if line.startswith("+"):
            if _matches_test_definition(line[1:], lang):
                added += 1
        elif line.startswith("-"):
            if _matches_test_definition(line[1:], lang):
                deleted += 1
    return added, deleted


def _matches_test_definition(line: str, language: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if language == "ruby":
        return bool(re.search(r"^(it|specify|test|scenario)\b", stripped))
    # Default to Python heuristics
    return bool(
        re.search(r"def\s+test_", stripped)
        or re.search(r"class\s+Test", stripped)
        or "self.assert" in stripped
        or "pytest.mark" in stripped
    )


def analyze_diff(files: List[Dict[str, object]], language: str | None) -> Dict[str, int | float]:
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

    lang = (language or "").lower()

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
        if _is_doc_file(path):
            stats["gh_diff_doc_files"] += 1
            classification = "doc"
        elif _is_test_file(path):
            stats["git_diff_test_churn"] += additions + deletions
            classification = "test"
        elif _is_source_file(path):
            stats["gh_diff_src_files"] += 1
            stats["git_diff_src_churn"] += additions + deletions
            classification = "src"
        else:
            stats["gh_diff_other_files"] += 1

        if classification == "test":
            added_tests, deleted_tests = _count_test_cases(patch, lang)
            stats["gh_diff_tests_added"] += added_tests
            stats["gh_diff_tests_deleted"] += deleted_tests

    return stats
