"""
Log Parsers - Framework-specific CI log parsers.

This module provides parsers for extracting test results from CI logs
for various test frameworks across multiple languages.

Structure:
- base.py: Base classes (ParsedLog, FrameworkParser)
- python.py: Python frameworks (pytest, unittest)
- ruby.py: Ruby frameworks (rspec, minitest, testunit, cucumber)
- java.py: Java frameworks (junit, testng)
- javascript.py: JavaScript/TypeScript frameworks (jest, mocha, jasmine, vitest)
- go.py: Go frameworks (gotest, gotestsum)
- cpp.py: C/C++ frameworks (gtest, catch2, ctest)
- registry.py: LogParserRegistry and TestLogParser

Supported Languages and Frameworks:
- Python: pytest, unittest
- Ruby: rspec, minitest, testunit, cucumber
- Java: junit, testng
- JavaScript/TypeScript: jest, mocha, jasmine, vitest
- Go: gotest, gotestsum
- C/C++: gtest, catch2, ctest

Usage:
    from app.pipeline.log_parsers import TestLogParser, ParsedLog

    parser = TestLogParser()
    result = parser.parse(log_text, language_hint="python")
    print(f"Tests: {result.tests_run}, Failed: {result.tests_failed}")
"""

from .base import ParsedLog, FrameworkParser
from .registry import TestLogParser, LogParserRegistry

__all__ = [
    "ParsedLog",
    "FrameworkParser",
    "TestLogParser",
    "LogParserRegistry",
]
