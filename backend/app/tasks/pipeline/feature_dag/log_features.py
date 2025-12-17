"""
Log-based Features for Hamilton Pipeline.

Extracts test results and other metrics from CI build logs:
- tr_log_tests_run_sum, tr_log_tests_failed_sum, tr_log_tests_skipped_sum, tr_log_tests_ok_sum
- tr_log_tests_fail_rate
- tr_log_testduration_sum
- tr_log_frameworks_all
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from hamilton.function_modifiers import extract_fields, tag

from app.tasks.pipeline.feature_dag._inputs import BuildLogsInput, RepoConfigInput
from app.tasks.pipeline.feature_dag._metadata import (
    feature_metadata,
    FeatureCategory,
    FeatureDataType,
    FeatureResource,
    OutputFormat,
)
from app.tasks.pipeline.feature_dag.log_parsers.registry import TestLogParser

logger = logging.getLogger(__name__)


# =============================================================================
# Test Log Parser Features
# =============================================================================


@extract_fields(
    {
        "tr_log_frameworks_all": list,
        "tr_log_tests_run_sum": int,
        "tr_log_tests_failed_sum": int,
        "tr_log_tests_skipped_sum": int,
        "tr_log_tests_ok_sum": int,
        "tr_log_tests_fail_rate": float,
        "tr_log_testduration_sum": float,
    }
)
@feature_metadata(
    display_name="Test Log Results",
    description="Test results extracted from CI build logs",
    category=FeatureCategory.BUILD_LOG,
    data_type=FeatureDataType.JSON,
    required_resources=[FeatureResource.BUILD_LOGS, FeatureResource.REPO],
    output_formats={
        "tr_log_frameworks_all": OutputFormat.COMMA_SEPARATED,
    },
)
@tag(group="build_log")
def test_log_features(
    build_logs: BuildLogsInput,
    repo_config: RepoConfigInput,
) -> Dict[str, Any]:
    """
    Parse CI build logs and extract test results.

    Returns aggregated test metrics across all job logs:
    - tr_log_frameworks_all: List of detected test frameworks
    - tr_log_tests_run_sum: Total tests run
    - tr_log_tests_failed_sum: Total tests failed
    - tr_log_tests_skipped_sum: Total tests skipped
    - tr_log_tests_ok_sum: Total tests passed
    - tr_log_tests_fail_rate: Failure rate (failed/run)
    - tr_log_testduration_sum: Total test duration in seconds
    """
    if not build_logs.is_available:
        return _empty_test_results()

    parser = TestLogParser()

    frameworks: Set[str] = set()
    tests_run_sum = 0
    tests_failed_sum = 0
    tests_skipped_sum = 0
    tests_ok_sum = 0
    test_duration_sum = 0.0

    language_hints = _get_language_hints(repo_config)
    allowed_frameworks = _get_allowed_frameworks(repo_config)

    for log_path_str in build_logs.log_files:
        try:
            log_path = Path(log_path_str)
            if not log_path.exists():
                continue

            content = log_path.read_text(errors="replace")

            # Try parsing with each language hint until we get a match
            parsed = None
            if language_hints:
                for lang_hint in language_hints:
                    parsed = parser.parse(
                        content,
                        language_hint=lang_hint,
                        allowed_frameworks=allowed_frameworks or None,
                    )
                    if parsed.framework:
                        break

            if not parsed or not parsed.framework:
                parsed = parser.parse(
                    content,
                    language_hint=None,
                    allowed_frameworks=allowed_frameworks or None,
                )

            if parsed.framework:
                frameworks.add(parsed.framework)

            tests_run_sum += parsed.tests_run
            tests_failed_sum += parsed.tests_failed
            tests_skipped_sum += parsed.tests_skipped
            tests_ok_sum += parsed.tests_ok

            if parsed.test_duration_seconds:
                test_duration_sum += parsed.test_duration_seconds

        except Exception as e:
            logger.warning(f"Failed to parse log {log_path_str}: {e}")

    # Derived metric
    fail_rate = tests_failed_sum / tests_run_sum if tests_run_sum > 0 else 0.0

    return {
        "tr_log_frameworks_all": list(frameworks),
        "tr_log_tests_run_sum": tests_run_sum,
        "tr_log_tests_failed_sum": tests_failed_sum,
        "tr_log_tests_skipped_sum": tests_skipped_sum,
        "tr_log_tests_ok_sum": tests_ok_sum,
        "tr_log_tests_fail_rate": fail_rate,
        "tr_log_testduration_sum": test_duration_sum,
    }


def _empty_test_results() -> Dict[str, Any]:
    """Return empty test results when logs are unavailable."""
    return {
        "tr_log_frameworks_all": [],
        "tr_log_tests_run_sum": 0,
        "tr_log_tests_failed_sum": 0,
        "tr_log_tests_skipped_sum": 0,
        "tr_log_tests_ok_sum": 0,
        "tr_log_tests_fail_rate": 0.0,
        "tr_log_testduration_sum": 0.0,
    }


def _get_allowed_frameworks(repo_config: RepoConfigInput) -> Optional[List[str]]:
    """Get allowed test frameworks from repo configuration."""
    if not repo_config.test_frameworks:
        return None
    return [
        f.lower() if isinstance(f, str) else str(f).lower()
        for f in repo_config.test_frameworks
    ]


def _get_language_hints(repo_config: RepoConfigInput) -> Optional[List[str]]:
    """Get all source languages from repo config for parser hints."""
    if not repo_config.source_languages:
        return None
    return [
        lang.lower() if isinstance(lang, str) else str(lang).lower()
        for lang in repo_config.source_languages
    ]
