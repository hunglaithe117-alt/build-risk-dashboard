"""
Base classes for log parsers.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Pattern


@dataclass
class ParsedLog:
    """Result of parsing a CI log."""

    framework: Optional[str]
    language: Optional[str]
    tests_run: int
    tests_failed: int
    tests_skipped: int
    test_duration_seconds: Optional[float]

    @property
    def tests_ok(self) -> int:
        return max(0, self.tests_run - self.tests_failed - self.tests_skipped)


class FrameworkParser(ABC):
    """Base class for framework-specific log parsers."""

    name: str  # e.g., "pytest", "junit"
    language: str  # e.g., "python", "java"

    @abstractmethod
    def parse(self, text: str) -> Optional[ParsedLog]:
        """
        Try to parse the log text.

        Returns ParsedLog if this framework's output is detected, None otherwise.
        """
        pass
