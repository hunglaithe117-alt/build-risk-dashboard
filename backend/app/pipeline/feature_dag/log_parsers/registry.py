"""
Log Parser Registry - Manages all framework-specific log parsers.

This module provides a unified interface to parse CI logs from various
test frameworks across different languages.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from .base import FrameworkParser, ParsedLog
from . import python as python_parsers
from . import ruby as ruby_parsers
from . import java as java_parsers
from . import javascript as javascript_parsers
from . import go as go_parsers
from . import cpp as cpp_parsers


class LogParserRegistry:
    """
    Central registry for log parsers.

    Organizes parsers by language and framework, providing:
    - Framework-specific parsing
    - Language-hint based parsing
    - Fallback to try all parsers
    """

    def __init__(self):
        self._parsers: Dict[str, List[FrameworkParser]] = {}
        self._framework_to_parser: Dict[str, FrameworkParser] = {}

        # Register all parsers
        self._register_parsers("python", python_parsers.PARSERS)
        self._register_parsers("ruby", ruby_parsers.PARSERS)
        self._register_parsers("java", java_parsers.PARSERS)
        self._register_parsers("javascript", javascript_parsers.PARSERS)
        self._register_parsers("typescript", javascript_parsers.PARSERS)  # Same as JS
        self._register_parsers("go", go_parsers.PARSERS)
        self._register_parsers("cpp", cpp_parsers.PARSERS)
        self._register_parsers("c++", cpp_parsers.PARSERS)  # Alias

    def _register_parsers(self, language: str, parsers: List[FrameworkParser]) -> None:
        """Register parsers for a language."""
        self._parsers[language] = parsers
        for parser in parsers:
            self._framework_to_parser[parser.name] = parser

    def get_supported_frameworks(self) -> List[str]:
        """Get list of all supported test frameworks."""
        return list(self._framework_to_parser.keys())

    def get_frameworks_by_language(self) -> Dict[str, List[str]]:
        """Get frameworks grouped by language."""
        return {
            lang: [p.name for p in parsers]
            for lang, parsers in self._parsers.items()
        }

    def get_languages(self) -> List[str]:
        """Get list of supported languages."""
        return list(self._parsers.keys())

    def parse(
        self,
        text: str,
        language_hint: Optional[str] = None,
        allowed_frameworks: Optional[Set[str]] = None,
    ) -> ParsedLog:
        """
        Parse log text and extract test results.

        Args:
            text: The log text to parse
            language_hint: Optional language hint to prioritize certain parsers
            allowed_frameworks: Optional set of frameworks to try (filter)

        Returns:
            ParsedLog with extracted metrics, or empty result if no match
        """
        allowed = (
            {f.lower() for f in allowed_frameworks}
            if allowed_frameworks
            else None
        )

        # Build ordered list of parsers to try
        parsers_to_try: List[FrameworkParser] = []

        # Prioritize language-specific parsers if hint provided
        if language_hint:
            lang_lower = language_hint.lower()
            if lang_lower in self._parsers:
                parsers_to_try.extend(self._parsers[lang_lower])

        # Add remaining parsers
        for lang, parsers in self._parsers.items():
            if language_hint and lang.lower() == language_hint.lower():
                continue  # Already added
            parsers_to_try.extend(parsers)

        # Try each parser
        for parser in parsers_to_try:
            if allowed and parser.name not in allowed:
                continue

            result = parser.parse(text)
            if result:
                return result

        # Fallback: no tests detected
        detected_language = (
            language_hint.lower() if language_hint
            else ("python" if "pytest" in text.lower() else None)
        )
        return ParsedLog(
            framework=None,
            language=detected_language,
            tests_run=0,
            tests_failed=0,
            tests_skipped=0,
            test_duration_seconds=None,
        )


# Global registry instance
_registry = LogParserRegistry()


class TestLogParser:
    """
    Main interface for parsing test logs.

    This class provides backwards compatibility with the old API
    while using the new registry-based architecture.
    """

    # Exposed for UI/config selection
    SUPPORTED_FRAMEWORKS: List[str] = _registry.get_supported_frameworks()
    FRAMEWORKS_BY_LANG: Dict[str, List[str]] = _registry.get_frameworks_by_language()

    def __init__(self):
        self._registry = _registry

    def parse(
        self,
        text: str,
        language_hint: Optional[str] = None,
        allowed_frameworks: Optional[List[str]] = None,
    ) -> ParsedLog:
        """
        Parse log text and extract test results.

        Args:
            text: The log text to parse
            language_hint: Optional language hint (e.g., "python", "ruby")
            allowed_frameworks: Optional list of frameworks to try

        Returns:
            ParsedLog with extracted metrics
        """
        allowed_set = set(allowed_frameworks) if allowed_frameworks else None
        return self._registry.parse(text, language_hint, allowed_set)
