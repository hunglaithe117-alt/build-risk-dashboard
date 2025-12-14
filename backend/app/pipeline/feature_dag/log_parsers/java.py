"""
Java test framework log parsers.

Supports:
- JUnit (via Maven/Gradle)
- TestNG
"""

from __future__ import annotations

import re
from typing import Optional

from .base import FrameworkParser, ParsedLog


class JUnitParser(FrameworkParser):
    """Parser for JUnit output (Maven/Gradle format)."""

    name = "junit"
    language = "java"

    PATTERN = re.compile(
        r"Tests run: (?P<tests>\d+), Failures: (?P<failures>\d+), "
        r"Errors: (?P<errors>\d+)(?:, Skipped: (?P<skipped>\d+))?",
        re.IGNORECASE,
    )
    TIME_PATTERN = re.compile(
        r"Tests run: .*? Time elapsed: (?P<duration>[\d\.]+) sec",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        tests = int(match.group("tests"))
        failures = int(match.group("failures"))
        errors = int(match.group("errors"))
        skipped = int(match.group("skipped") or 0)

        duration = None
        duration_match = self.TIME_PATTERN.search(text)
        if duration_match:
            duration = float(duration_match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=tests,
            tests_failed=failures + errors,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


class TestNGParser(FrameworkParser):
    """Parser for TestNG output."""

    name = "testng"
    language = "java"

    PATTERN = re.compile(
        r"Total tests run:\s*(?P<tests>\d+), Failures: (?P<failures>\d+), "
        r"Skips: (?P<skipped>\d+)",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        tests = int(match.group("tests"))
        failures = int(match.group("failures"))
        skipped = int(match.group("skipped"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=tests,
            tests_failed=failures,
            tests_skipped=skipped,
            test_duration_seconds=None,  # TestNG doesn't always provide duration
        )


# All parsers for this language
PARSERS = [JUnitParser(), TestNGParser()]
