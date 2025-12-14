"""
C/C++ test framework log parsers.

Supports:
- Google Test (gtest)
- Catch2
- CTest (CMake)
"""

from __future__ import annotations

import re
from typing import Optional

from .base import FrameworkParser, ParsedLog


class GTestParser(FrameworkParser):
    """Parser for Google Test (gtest) output."""

    name = "gtest"
    language = "cpp"

    # [==========] 10 tests from 3 test suites ran. (123 ms total)
    # [  PASSED  ] 8 tests.
    # [  FAILED  ] 2 tests.
    # [  SKIPPED ] 1 test.
    
    TOTAL_PATTERN = re.compile(
        r"\[=+\]\s+(?P<total>\d+)\s+tests?\s+from\s+\d+\s+test\s+(?:suites?|cases?)\s+ran\."
        r"\s*\((?P<duration>\d+)\s*ms\s+total\)",
        re.IGNORECASE,
    )
    PASSED_PATTERN = re.compile(
        r"\[\s*PASSED\s*\]\s+(?P<passed>\d+)\s+tests?",
        re.IGNORECASE,
    )
    FAILED_PATTERN = re.compile(
        r"\[\s*FAILED\s*\]\s+(?P<failed>\d+)\s+tests?",
        re.IGNORECASE,
    )
    SKIPPED_PATTERN = re.compile(
        r"\[\s*(?:SKIPPED|DISABLED)\s*\]\s+(?P<skipped>\d+)\s+tests?",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        total_match = self.TOTAL_PATTERN.search(text)
        if not total_match:
            return None

        total = int(total_match.group("total"))
        duration_ms = int(total_match.group("duration"))

        passed = 0
        passed_match = self.PASSED_PATTERN.search(text)
        if passed_match:
            passed = int(passed_match.group("passed"))

        failed = 0
        failed_match = self.FAILED_PATTERN.search(text)
        if failed_match:
            failed = int(failed_match.group("failed"))

        skipped = 0
        skipped_match = self.SKIPPED_PATTERN.search(text)
        if skipped_match:
            skipped = int(skipped_match.group("skipped"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=total,
            tests_failed=failed,
            tests_skipped=skipped,
            test_duration_seconds=duration_ms / 1000.0,
        )


class Catch2Parser(FrameworkParser):
    """Parser for Catch2 output."""

    name = "catch2"
    language = "cpp"

    # ===============================================================================
    # All tests passed (42 assertions in 10 test cases)
    # test cases: 10 | 8 passed | 2 failed
    # assertions: 42 | 38 passed | 4 failed
    
    TEST_CASES_PATTERN = re.compile(
        r"test\s+cases:\s*(?P<total>\d+)\s*\|\s*(?P<passed>\d+)\s+passed"
        r"(?:\s*\|\s*(?P<failed>\d+)\s+failed)?",
        re.IGNORECASE,
    )
    ALL_PASSED_PATTERN = re.compile(
        r"All\s+tests\s+passed\s*\((?P<assertions>\d+)\s+assertions?\s+in\s+(?P<cases>\d+)\s+test\s+cases?\)",
        re.IGNORECASE,
    )
    DURATION_PATTERN = re.compile(
        r"(?P<duration>[\d\.]+)\s*(?:s|seconds?)",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        # Try detailed format first
        match = self.TEST_CASES_PATTERN.search(text)
        if match:
            total = int(match.group("total"))
            passed = int(match.group("passed"))
            failed = int(match.group("failed") or 0)
            
            return ParsedLog(
                framework=self.name,
                language=self.language,
                tests_run=total,
                tests_failed=failed,
                tests_skipped=0,
                test_duration_seconds=None,
            )

        # Try "All tests passed" format
        all_passed = self.ALL_PASSED_PATTERN.search(text)
        if all_passed:
            cases = int(all_passed.group("cases"))
            return ParsedLog(
                framework=self.name,
                language=self.language,
                tests_run=cases,
                tests_failed=0,
                tests_skipped=0,
                test_duration_seconds=None,
            )

        return None


class CTestParser(FrameworkParser):
    """Parser for CTest (CMake) output."""

    name = "ctest"
    language = "cpp"

    # 100% tests passed, 0 tests failed out of 10
    # Total Test time (real) =   5.67 sec
    
    SUMMARY_PATTERN = re.compile(
        r"(?P<percent>\d+)%\s+tests\s+passed,\s*(?P<failed>\d+)\s+tests?\s+failed\s+out\s+of\s+(?P<total>\d+)",
        re.IGNORECASE,
    )
    TIME_PATTERN = re.compile(
        r"Total\s+Test\s+time\s*\(real\)\s*=\s*(?P<duration>[\d\.]+)\s*sec",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.SUMMARY_PATTERN.search(text)
        if not match:
            return None

        total = int(match.group("total"))
        failed = int(match.group("failed"))

        duration = None
        time_match = self.TIME_PATTERN.search(text)
        if time_match:
            duration = float(time_match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=total,
            tests_failed=failed,
            tests_skipped=0,
            test_duration_seconds=duration,
        )


# All parsers for this language
PARSERS = [GTestParser(), Catch2Parser(), CTestParser()]
