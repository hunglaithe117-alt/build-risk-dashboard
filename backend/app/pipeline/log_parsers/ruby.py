"""
Ruby test framework log parsers.

Supports:
- RSpec
- Minitest
- Test::Unit
- Cucumber
"""

from __future__ import annotations

import re
from typing import Optional

from .base import FrameworkParser, ParsedLog


class RSpecParser(FrameworkParser):
    """Parser for RSpec output."""

    name = "rspec"
    language = "ruby"

    PATTERN = re.compile(
        r"(?P<examples>\d+)\s+examples?,\s+(?P<failures>\d+)\s+failures?"
        r"(?:,\s+(?P<pending>\d+)\s+pending)?",
        re.IGNORECASE,
    )
    DURATION_PATTERN = re.compile(
        r"Finished in\s+(?P<duration>[\d\.]+)\s+seconds?",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        examples = int(match.group("examples"))
        failures = int(match.group("failures"))
        pending = int(match.group("pending") or 0)

        duration_match = self.DURATION_PATTERN.search(text)
        duration = float(duration_match.group("duration")) if duration_match else None

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=examples,
            tests_failed=failures,
            tests_skipped=pending,
            test_duration_seconds=duration,
        )


class MinitestParser(FrameworkParser):
    """Parser for Minitest output."""

    name = "minitest"
    language = "ruby"

    PATTERN = re.compile(
        r"(?P<runs>\d+)\s+runs?,\s+(?P<assertions>\d+)\s+assertions?,\s+"
        r"(?P<failures>\d+)\s+failures?,\s+(?P<errors>\d+)\s+errors?"
        r"(?:,\s+(?P<skips>\d+)\s+skips?)?",
        re.IGNORECASE,
    )
    DURATION_PATTERN = re.compile(
        r"Finished in\s+(?P<duration>[\d\.]+)s",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        runs = int(match.group("runs"))
        failures = int(match.group("failures"))
        errors = int(match.group("errors"))
        skips = int(match.group("skips") or 0)

        duration_match = self.DURATION_PATTERN.search(text)
        duration = float(duration_match.group("duration")) if duration_match else None

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=runs,
            tests_failed=failures + errors,
            tests_skipped=skips,
            test_duration_seconds=duration,
        )


class TestUnitParser(FrameworkParser):
    """Parser for Test::Unit output."""

    name = "testunit"
    language = "ruby"

    PATTERN = re.compile(
        r"(?P<tests>\d+)\s+tests,\s+(?P<assertions>\d+)\s+assertions,\s+"
        r"(?P<failures>\d+)\s+failures,\s+(?P<errors>\d+)\s+errors"
        r"(?:,\s+(?P<pendings>\d+)\s+pendings)?"
        r"(?:,\s+(?P<omissions>\d+)\s+omissions)?"
        r"(?:,\s+(?P<notifications>\d+)\s+notifications)?",
        re.IGNORECASE,
    )
    DURATION_PATTERN = re.compile(
        r"Finished in\s+(?P<duration>[\d\.]+)\s+seconds",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.PATTERN.search(text)
        if not match:
            return None

        tests = int(match.group("tests"))
        failures = int(match.group("failures"))
        errors = int(match.group("errors"))
        pendings = int(match.group("pendings") or 0)
        omissions = int(match.group("omissions") or 0)

        duration_match = self.DURATION_PATTERN.search(text)
        duration = float(duration_match.group("duration")) if duration_match else None

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=tests,
            tests_failed=failures + errors,
            tests_skipped=pendings + omissions,
            test_duration_seconds=duration,
        )


class CucumberParser(FrameworkParser):
    """Parser for Cucumber output."""

    name = "cucumber"
    language = "ruby"

    SCENARIO_PATTERN = re.compile(
        r"(?P<total>\d+)\s+scenarios?\s*\("
        r"(?:(?P<failed>\d+)\s+failed)?"
        r"(?:,?\s*(?P<undefined>\d+)\s+undefined)?"
        r"(?:,?\s*(?P<passed>\d+)\s+passed)?"
        r"\)",
        re.IGNORECASE,
    )
    DURATION_PATTERN = re.compile(
        r"(?P<minutes>\d+)m(?P<seconds>[\d\.]+)s",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.SCENARIO_PATTERN.search(text)
        if not match:
            return None

        total = int(match.group("total"))
        failed = int(match.group("failed") or 0)
        undefined = int(match.group("undefined") or 0)

        duration = None
        duration_match = self.DURATION_PATTERN.search(text)
        if duration_match:
            minutes = int(duration_match.group("minutes"))
            seconds = float(duration_match.group("seconds"))
            duration = minutes * 60 + seconds

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=total,
            tests_failed=failed,
            tests_skipped=undefined,
            test_duration_seconds=duration,
        )


# All parsers for this language
PARSERS = [RSpecParser(), MinitestParser(), TestUnitParser(), CucumberParser()]
