"""Utilities for translating GitHub compare payloads into feature metrics."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


DOC_PREFIXES = ("docs/", "doc/", "documentation/")
DOC_EXTENSIONS = (".md", ".rst", ".adoc", ".txt")
TEST_DIR_HINTS = ("tests/", "test/", "spec/")


def _strip_shell_comments(line: str) -> str:
    """Strip shell-style comments (# ...) from a line. Used for Python and Ruby."""
    if "#" in line:
        return line.split("#", 1)[0]
    return line


def _strip_c_comments(line: str) -> str:
    """Strip C-style single-line comments (// ...) from a line. Used for Java."""
    if "//" in line:
        return line.split("//", 1)[0]
    return line


def _strip_comments(line: str, language: str) -> str:
    """Strip comments from a line based on language."""
    lang = language.lower()
    if lang in ("python", "ruby"):
        return _strip_shell_comments(line)
    elif lang == "java":
        return _strip_c_comments(line)
    return line


def _is_doc_file(path: str) -> bool:
    lowered = path.lower()
    return lowered.startswith(DOC_PREFIXES) or lowered.endswith(DOC_EXTENSIONS)


def _is_test_file(path: str, language: str | None = None) -> bool:
    """
    Determine if a file is a test file based on language-specific heuristics.
    Matches TravisTorrent logic.
    """
    lang = (language or "").lower()
    lowered = path.lower()

    if lang == "ruby" or path.endswith(".rb"):
        # Ruby: ends with .rb AND (contains test/, tests/, or spec/) AND (does NOT contain lib/)
        if not path.endswith(".rb"):
            return False
        has_test_dir = any(x in lowered for x in ["test/", "tests/", "spec/"])
        has_lib_dir = "lib/" in lowered
        return has_test_dir and not has_lib_dir

    if lang == "java" or path.endswith(".java"):
        # Java: ends with .java AND (contains test/ or tests/ OR ends with Test.java)
        if not path.endswith(".java"):
            return False
        has_test_dir = any(x in lowered for x in ["test/", "tests/"])
        is_test_suffix = bool(re.search(r"[tT]est\.java$", path))
        return has_test_dir or is_test_suffix

    if lang == "python" or path.endswith(".py"):
        # Python: ends with .py AND (starts with test_ OR ends with _test.py OR is test.py OR contains test/ or tests/)
        if not path.endswith(".py"):
            return False
        # Note: TravisTorrent Ruby regex for Python test files:
        # path.match(/test_.+/i) or path.match(/.+_test/i) or path.match(/test.py/i) or path.match(/tests?\//i)
        # This implies checking the full path for "test_" or "_test" which is broad, but we stick to it.
        # However, usually these apply to filenames. The Ruby code `path.match` applies to the full path string.

        # Check for test directories first
        if any(x in lowered for x in ["test/", "tests/"]):
            return True

        filename = path.split("/")[-1]
        return (
            filename.lower().startswith("test_")
            or filename.lower().endswith("_test.py")
            or filename.lower() == "test.py"
        )

    # Fallback / Generic
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
        # Strip the diff prefix
        if line.startswith("+"):
            clean_line = _strip_comments(line[1:], lang)
            if _matches_test_definition(clean_line, lang):
                added += 1
        elif line.startswith("-"):
            clean_line = _strip_comments(line[1:], lang)
            if _matches_test_definition(clean_line, lang):
                deleted += 1
    return added, deleted


def _matches_test_definition(line: str, language: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    lang = language.lower()

    if lang == "ruby":
        # Ruby: ^ *def +.*test.* OR ^\s*should\s+.*\s+(do|{) OR ^\s*it\s+.*\s+(do|{)
        return bool(
            re.match(r"^ *def +.*test.*", stripped)
            or re.match(r"^\s*should\s+.*\s+(do|{)", stripped)
            or re.match(r"^\s*it\s+.*\s+(do|{)", stripped)
        )

    if lang == "java":
        # Java: @Test OR (public|protected|private|static|\s) +[\w<>\[\]]+\s+(.*[tT]est) *\([^\)]*\) *(\{?|[^;])
        return bool(
            re.search(r"@Test", stripped)
            or re.search(
                r"(public|protected|private|static|\s) +[\w<>\[\]]+\s+(.*[tT]est) *\([^\)]*\) *(\{?|[^;])",
                stripped,
            )
        )

    if lang == "python":
        # Python: \s*def\s* test_(.*)\(.*\):
        return bool(re.search(r"\s*def\s* test_(.*)\(.*\):", stripped))

    # Default to generic if language not matched (though we usually know it)
    return bool(
        re.search(r"def\s+test_", stripped)
        or re.search(r"class\s+Test", stripped)
        or "self.assert" in stripped
        or "pytest.mark" in stripped
    )


def _matches_assertion(line: str, language: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False

    lang = language.lower()

    if lang == "ruby":
        # Ruby: assert, .should, .expect, .must_, .wont_
        # \s+should\s*[({]?
        # \s+expect\s*[({]?
        return bool(
            re.search(r"assert", stripped)
            or re.search(r"\.should", stripped)
            or re.search(r"\.expect", stripped)
            or re.search(r"\.must_", stripped)
            or re.search(r"\.wont_", stripped)
            or re.search(r"(^|\s+)should\s*[({]?", stripped)
            or re.search(r"(^|\s+)expect\s*[({]?", stripped)
        )

    if lang == "java":
        # Java: assert
        return bool(re.search(r"assert", stripped))

    if lang == "python":
        # Python: assert([A-Z]\w*)?, (with)?\s*(pytest\.)?raises, (pytest.)?approx
        return bool(
            re.search(r"assert([A-Z]\w*)?", stripped)
            or re.search(r"(with)?\s*(pytest\.)?raises", stripped)
            or re.search(r"(pytest\.)?approx", stripped)
        )

    # Default
    return "assert" in stripped


def analyze_diff(
    files: List[Dict[str, object]], language: str | None
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
