"""
Test Log Parser Node.

Extracts test results from CI build logs:
- tr_log_tests_run_sum, tr_log_tests_failed_sum, tr_log_tests_skipped_sum, tr_log_tests_ok_sum
- tr_log_tests_fail_rate
- tr_log_testduration_sum
- tr_log_frameworks_all
"""

from typing import Any, Dict, Set

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.log_storage import LogStorageHandle
from app.pipeline.log_parsers import TestLogParser


@register_feature(
    name="test_log_parser",
    requires_resources={ResourceNames.LOG_STORAGE},
    provides={
        "tr_log_frameworks_all",
        "tr_log_tests_run_sum",
        "tr_log_tests_failed_sum",
        "tr_log_tests_skipped_sum",
        "tr_log_tests_ok_sum",
        "tr_log_tests_fail_rate",
        "tr_log_testduration_sum",
    },
    group="build_log",
    priority=5,  # Lower priority - requires expensive log parsing
)
class TestLogParserNode(FeatureNode):
    """Parses CI logs to extract test results."""

    def __init__(self):
        self.parser = TestLogParser()

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        log_storage: LogStorageHandle = context.get_resource(ResourceNames.LOG_STORAGE)
        repo = context.repo

        if not log_storage.has_logs:
            return self._empty_result()

        frameworks: Set[str] = set()
        tests_run_sum = 0
        tests_failed_sum = 0
        tests_skipped_sum = 0
        tests_ok_sum = 0
        test_duration_sum = 0.0

        for log_file in log_storage.log_files:
            try:
                content = log_file.read()
                allowed_frameworks = self._get_allowed_frameworks(repo)
                language_hint = self._get_language_hint(repo)

                parsed = self.parser.parse(
                    content,
                    language_hint=language_hint,
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
                import logging

                logging.getLogger(__name__).warning(
                    f"Failed to parse log {log_file.path}: {e}"
                )

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

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "tr_log_frameworks_all": [],
            "tr_log_tests_run_sum": 0,
            "tr_log_tests_failed_sum": 0,
            "tr_log_tests_skipped_sum": 0,
            "tr_log_tests_ok_sum": 0,
            "tr_log_tests_fail_rate": 0.0,
            "tr_log_testduration_sum": 0.0,
        }

    def _get_allowed_frameworks(self, repo) -> list:
        if not repo or not getattr(repo, "test_frameworks", None):
            return []
        return [
            f.value.lower() if hasattr(f, "value") else str(f).lower()
            for f in repo.test_frameworks
        ]

    def _get_language_hint(self, repo) -> str | None:
        if not repo or not repo.source_languages:
            return None
        lang = repo.source_languages[0]
        return lang.lower() if isinstance(lang, str) else str(lang).lower()
