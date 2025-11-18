"""Unit tests for the pytest/RSpec log parser."""
from app.services.log_parser import TestLogParser


def test_pytest_parser_detects_pass_fail_skip():
    parser = TestLogParser()
    log = """
    ============================= test session starts =============================
    collected 5 items

    ====================== 3 passed, 1 failed, 1 skipped in 12.34s =====================
    """.strip()

    result = parser.parse(log, language_hint="python")

    assert result.framework == "pytest"
    assert result.language == "python"
    assert result.tests_run == 5
    assert result.tests_failed == 1
    assert result.tests_skipped == 1
    assert result.tests_ok == 3
    assert result.duration_seconds == 12.34


def test_rspec_parser_detects_examples_and_pending():
    parser = TestLogParser()
    log = """
    Finished in 3.45 seconds (files took 1.2 seconds to load)
    4 examples, 1 failures, 1 pending
    """.strip()

    result = parser.parse(log, language_hint="ruby")

    assert result.framework == "rspec"
    assert result.language == "ruby"
    assert result.tests_run == 4
    assert result.tests_failed == 1
    assert result.tests_skipped == 1
    assert result.tests_ok == 2
    assert result.test_duration_seconds == 3.45


def test_minitest_parser_detects_runs_and_failures():
    parser = TestLogParser()
    log = """
    Finished in 0.12345s, 4 runs, 10 assertions, 1 failures, 0 errors, 1 skips
    """.strip()

    result = parser.parse(log, language_hint="ruby")

    assert result.framework == "minitest"
    assert result.language == "ruby"
    assert result.tests_run == 4
    assert result.tests_failed == 1
    assert result.tests_skipped == 1
    assert result.tests_ok == 2
    assert result.duration_seconds == 0.12345
