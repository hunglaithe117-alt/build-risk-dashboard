"""Structured parsers for common CI test output (pytest/unittest/RSpec)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedLog:
    framework: Optional[str]
    language: Optional[str]
    tests_run: int
    tests_failed: int
    tests_skipped: int
    duration_seconds: Optional[float]
    test_duration_seconds: Optional[float]

    @property
    def tests_ok(self) -> int:
        return max(0, self.tests_run - self.tests_failed - self.tests_skipped)


class TestLogParser:
    """Detects test framework and extracts aggregate metrics."""

    PYTEST_PATTERN = re.compile(
        r"=+\s*(?P<passed>\d+)\s+passed(?:,\s*(?P<failed>\d+)\s+failed)?(?:,\s*(?P<skipped>\d+)\s+skipped)?(?:,\s*(?P<xfailed>\d+)\s+xfailed)?\s+in\s+(?P<duration>[\d\.]+)s",
        re.IGNORECASE,
    )
    UNITTEST_PATTERN = re.compile(r"Ran\s+(?P<tests>\d+)\s+tests\s+in\s+(?P<duration>[\d\.]+)s", re.IGNORECASE)
    UNITTEST_STATUS_PATTERN = re.compile(
        r"FAILED\s+\((?:failures=(?P<failures>\d+))?(?:,\s*errors=(?P<errors>\d+))?(?:,\s*skipped=(?P<skipped>\d+))?",
        re.IGNORECASE,
    )
    RSPec_PATTERN = re.compile(
        r"(?P<examples>\d+)\s+examples?,\s+(?P<failures>\d+)\s+failures?(?:,\s+(?P<pending>\d+)\s+pending)?",
        re.IGNORECASE,
    )
    RSPec_DURATION = re.compile(r"Finished in\s+(?P<duration>[\d\.]+)\s+seconds?", re.IGNORECASE)
    MINITEST_PATTERN = re.compile(
        r"(?P<runs>\d+)\s+runs?,\s+(?P<assertions>\d+)\s+assertions?,\s+(?P<failures>\d+)\s+failures?,\s+(?P<errors>\d+)\s+errors?(?:,\s+(?P<skips>\d+)\s+skips?)?",
        re.IGNORECASE,
    )
    MINITEST_DURATION = re.compile(r"Finished in\s+(?P<duration>[\d\.]+)s", re.IGNORECASE)

    def parse(self, text: str, language_hint: Optional[str] = None) -> ParsedLog:
        language_hint = (language_hint or "").lower()
        framework = None

        match = self.PYTEST_PATTERN.search(text)
        if match:
            framework = "pytest"
            failed = int(match.group("failed") or 0)
            skipped = int(match.group("skipped") or 0)
            passed = int(match.group("passed"))
            duration = float(match.group("duration"))
            return ParsedLog(framework, "python", passed + failed + skipped, failed, skipped, duration, duration)

        unit = self.UNITTEST_PATTERN.search(text)
        if unit:
            framework = "unittest"
            tests = int(unit.group("tests"))
            duration = float(unit.group("duration"))
            status = self.UNITTEST_STATUS_PATTERN.search(text)
            failures = int(status.group("failures") or 0) if status else 0
            errors = int(status.group("errors") or 0) if status else 0
            skipped = int(status.group("skipped") or 0) if status else 0
            failed_total = failures + errors
            return ParsedLog(framework, "python", tests, failed_total, skipped, duration, None)

        rspec = self.RSPec_PATTERN.search(text)
        if rspec:
            framework = "rspec"
            examples = int(rspec.group("examples"))
            failures = int(rspec.group("failures"))
            pending = int(rspec.group("pending") or 0)
            duration_match = self.RSPec_DURATION.search(text)
            duration = float(duration_match.group("duration")) if duration_match else None
            return ParsedLog(framework, "ruby", examples, failures, pending, duration, duration)

        minitest = self.MINITEST_PATTERN.search(text)
        if minitest:
            framework = "minitest"
            runs = int(minitest.group("runs"))
            failures = int(minitest.group("failures"))
            errors = int(minitest.group("errors"))
            skips = int(minitest.group("skips") or 0)
            duration_match = self.MINITEST_DURATION.search(text)
            duration = float(duration_match.group("duration")) if duration_match else None
            failed_total = failures + errors
            return ParsedLog(framework, "ruby", runs, failed_total, skips, duration, duration)

        # Fallback: no tests detected
        detected_language = language_hint or ("python" if "pytest" in text.lower() else None)
        return ParsedLog(framework, detected_language, 0, 0, 0, None, None)
