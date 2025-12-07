"""
Go test framework log parsers.

Supports:
- go test (standard library testing)
"""

from __future__ import annotations

import re
from typing import Optional

from .base import FrameworkParser, ParsedLog


class GoTestParser(FrameworkParser):
    """Parser for go test output."""

    name = "gotest"
    language = "go"

    # ok      github.com/user/pkg    0.123s
    # FAIL    github.com/user/pkg    0.456s
    # --- PASS: TestFoo (0.00s)
    # --- FAIL: TestBar (0.00s)
    # --- SKIP: TestBaz (0.00s)
    
    # Summary pattern: ok/FAIL package duration
    SUMMARY_PATTERN = re.compile(
        r"(?:ok|FAIL)\s+\S+\s+(?P<duration>[\d\.]+)s",
        re.MULTILINE,
    )
    
    PASS_PATTERN = re.compile(r"---\s+PASS:", re.MULTILINE)
    FAIL_PATTERN = re.compile(r"---\s+FAIL:", re.MULTILINE)
    SKIP_PATTERN = re.compile(r"---\s+SKIP:", re.MULTILINE)

    def parse(self, text: str) -> Optional[ParsedLog]:
        # Count test results
        passed = len(self.PASS_PATTERN.findall(text))
        failed = len(self.FAIL_PATTERN.findall(text))
        skipped = len(self.SKIP_PATTERN.findall(text))

        # If no individual tests found, not a go test output
        if passed + failed + skipped == 0:
            return None

        # Get total duration from summary lines
        durations = self.SUMMARY_PATTERN.findall(text)
        duration = sum(float(d) for d in durations) if durations else None

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=passed + failed + skipped,
            tests_failed=failed,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


class GotestsumParser(FrameworkParser):
    """Parser for gotestsum output (enhanced go test runner)."""

    name = "gotestsum"
    language = "go"

    # DONE 123 tests in 4.567s
    # DONE 123 tests, 2 failures in 4.567s
    # DONE 123 tests, 2 skipped in 4.567s
    SUMMARY_PATTERN = re.compile(
        r"DONE\s+(?P<total>\d+)\s+tests?"
        r"(?:,\s*(?P<failures>\d+)\s+(?:failures?|failed))?"
        r"(?:,\s*(?P<skipped>\d+)\s+skipped)?"
        r"\s+in\s+(?P<duration>[\d\.]+)s",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> Optional[ParsedLog]:
        match = self.SUMMARY_PATTERN.search(text)
        if not match:
            return None

        total = int(match.group("total"))
        failures = int(match.group("failures") or 0)
        skipped = int(match.group("skipped") or 0)
        duration = float(match.group("duration"))

        return ParsedLog(
            framework=self.name,
            language=self.language,
            tests_run=total,
            tests_failed=failures,
            tests_skipped=skipped,
            test_duration_seconds=duration,
        )


# All parsers for this language
PARSERS = [GoTestParser(), GotestsumParser()]
