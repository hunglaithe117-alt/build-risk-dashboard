"""
Analyzers - Code analysis utilities for the pipeline.

This module provides utilities for:
- Diff analysis (test file detection, churn calculation)
- Code metric extraction
"""

from .diff_analyzer import (
    _count_test_cases,
    _is_doc_file,
    _is_source_file,
    _is_test_file,
    _matches_assertion,
    _matches_test_definition,
    _strip_c_comments,
    _strip_comments,
    _strip_shell_comments,
    analyze_diff,
)

__all__ = [
    "analyze_diff",
    "_is_test_file",
    "_is_source_file",
    "_is_doc_file",
    "_count_test_cases",
    "_matches_test_definition",
    "_matches_assertion",
    "_strip_comments",
    "_strip_shell_comments",
    "_strip_c_comments",
]
