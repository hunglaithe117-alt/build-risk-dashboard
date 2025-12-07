"""
Python test framework log parsers.

Supports:
- pytest
- unittest
"""

from __future__ import annotations

import re
from typing import Optional

from .base import FrameworkParser, ParsedLog


class PytestParser(FrameworkParser):
    """Parser for pytest output."""

    name = "pytest"
    language = "python"

    PATTERN = re.compile(
        r"=+\s*(?P<passed>\d+)\s+passed"
        r"(?:,\s*(?P<failed>\d+)\s+failed)?"
        r"(?:,\s*(?P<skipped>\d+)\s+skipped)?"
        r"(?:,\s*(?P<xfailed>\d+)\s+xfailed)?"
        r"\s+in\s+(?P<duration>[\d\.]+)s",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        passed = int(match.group("passed"))
        failed = int(match.group("failed") or 0)
        skipped = int(match.group("skipped") or 0)
        duration = float(match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=passed + failed + skipped,
            tests_failed=failed,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


class UnittestParser(FrameworkParser):
    """Parser for Python unittest output."""

    name = "unittest"
    language = "python"

    PATTERN = re.compile(
        r"Ran\s+(?P<tests>\d+)\s+tests\s+in\s+(?P<duration>[\d\.]+)s",
        re.IGNORECASE,
    )
    STATUS_PATTERN = re.compile(
        r"FAILED\s+\("
        r"(?:failures=(?P<failures>\d+))?"
        r"(?:,\s*errors=(?P<errors>\d+))?"
        r"(?:,\s*skipped=(?P<skipped>\d+))?",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        tests = int(match.group("tests"))
        duration = float(match.group("duration"))

        status = self.STATUS_PATTERN.search(text)
        failures = int(status.group("failures") or 0) if status else 0
        errors = int(status.group("errors") or 0) if status else 0
        skipped = int(status.group("skipped") or 0) if status else 0

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=tests,
            tests_failed=failures + errors,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


# All parsers for this language
PARSERS = [PytestParser(), UnittestParser()]
