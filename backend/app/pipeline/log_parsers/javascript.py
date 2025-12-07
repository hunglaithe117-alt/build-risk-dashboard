"""
JavaScript/TypeScript test framework log parsers.

Supports:
- Jest
- Mocha
- Jasmine
"""

from __future__ import annotations

import re
from typing import Optional

from .base import FrameworkParser, ParsedLog


class JestParser(FrameworkParser):
    """Parser for Jest output."""

    name = "jest"
    language = "javascript"

    # Jest summary: Tests: 5 passed, 2 failed, 7 total
    TESTS_PATTERN = re.compile(
        r"Tests:\s+(?:(?P<passed>\d+)\s+passed,?\s*)?"
        r"(?:(?P<failed>\d+)\s+failed,?\s*)?"
        r"(?:(?P<skipped>\d+)\s+skipped,?\s*)?"
        r"(?P<total>\d+)\s+total",
        re.IGNORECASE,
    )
    # Time: 2.345s
    TIME_PATTERN = re.compile(
        r"Time:\s+(?P<duration>[\d\.]+)\s*s",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.TESTS_PATTERN.search(text)
        if not match:
            return None

        total = int(match.group("total"))
        passed = int(match.group("passed") or 0)
        failed = int(match.group("failed") or 0)
        skipped = int(match.group("skipped") or 0)

        duration = None
        time_match = self.TIME_PATTERN.search(text)
        if time_match:
            duration = float(time_match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=total,
            tests_failed=failed,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


class MochaParser(FrameworkParser):
    """Parser for Mocha output."""

    name = "mocha"
    language = "javascript"

    # 5 passing (2s)
    # 2 failing
    # 1 pending
    PASSING_PATTERN = re.compile(
        r"(?P<passing>\d+)\s+passing\s*\((?:(?P<duration_ms>\d+)ms|(?P<duration_s>[\d\.]+)s)\)",
        re.IGNORECASE,
    )
    FAILING_PATTERN = re.compile(
        r"(?P<failing>\d+)\s+failing",
        re.IGNORECASE,
    )
    PENDING_PATTERN = re.compile(
        r"(?P<pending>\d+)\s+pending",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        passing_match = self.PASSING_PATTERN.search(text)
        if not passing_match:
            return None

        passing = int(passing_match.group("passing"))
        
        # Get duration
        duration = None
        if passing_match.group("duration_ms"):
            duration = int(passing_match.group("duration_ms")) / 1000.0
        elif passing_match.group("duration_s"):
            duration = float(passing_match.group("duration_s"))

        failing = 0
        failing_match = self.FAILING_PATTERN.search(text)
        if failing_match:
            failing = int(failing_match.group("failing"))

        pending = 0
        pending_match = self.PENDING_PATTERN.search(text)
        if pending_match:
            pending = int(pending_match.group("pending"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=passing + failing + pending,
            tests_failed=failing,
            tests_skipped=pending,
            test_duration_seconds=duration,
        )


class JasmineParser(FrameworkParser):
    """Parser for Jasmine output."""

    name = "jasmine"
    language = "javascript"

    # 5 specs, 2 failures, 1 pending
    # Finished in 0.123 seconds
    SPECS_PATTERN = re.compile(
        r"(?P<specs>\d+)\s+specs?,\s*(?P<failures>\d+)\s+failures?"
        r"(?:,\s*(?P<pending>\d+)\s+pending)?",
        re.IGNORECASE,
    )
    TIME_PATTERN = re.compile(
        r"Finished in\s+(?P<duration>[\d\.]+)\s+seconds?",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.SPECS_PATTERN.search(text)
        if not match:
            return None

        specs = int(match.group("specs"))
        failures = int(match.group("failures"))
        pending = int(match.group("pending") or 0)

        duration = None
        time_match = self.TIME_PATTERN.search(text)
        if time_match:
            duration = float(time_match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=specs,
            tests_failed=failures,
            tests_skipped=pending,
            test_duration_seconds=duration,
        )


class VitestParser(FrameworkParser):
    """Parser for Vitest output."""

    name = "vitest"
    language = "javascript"

    # Tests  5 passed | 2 failed | 1 skipped (8)
    # Duration  2.34s
    TESTS_PATTERN = re.compile(
        r"Tests\s+(?:(?P<passed>\d+)\s+passed\s*\|?\s*)?"
        r"(?:(?P<failed>\d+)\s+failed\s*\|?\s*)?"
        r"(?:(?P<skipped>\d+)\s+skipped\s*\|?\s*)?"
        r"\((?P<total>\d+)\)",
        re.IGNORECASE,
    )
    TIME_PATTERN = re.compile(
        r"Duration\s+(?P<duration>[\d\.]+)s",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.TESTS_PATTERN.search(text)
        if not match:
            return None

        total = int(match.group("total"))
        passed = int(match.group("passed") or 0)
        failed = int(match.group("failed") or 0)
        skipped = int(match.group("skipped") or 0)

        duration = None
        time_match = self.TIME_PATTERN.search(text)
        if time_match:
            duration = float(time_match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=total,
            tests_failed=failed,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


# All parsers for this language
PARSERS = [JestParser(), MochaParser(), JasmineParser(), VitestParser()]
