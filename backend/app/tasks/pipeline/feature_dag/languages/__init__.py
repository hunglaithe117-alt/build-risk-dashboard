"""
Language-specific strategies for test detection and code analysis.

This module provides language-aware strategies for:
- Detecting test files vs source files
- Parsing test definitions
- Matching assertions
- Stripping comments

Used by RepoSnapshotNode and other pipeline features.
"""

from .base import LanguageStrategy
from .cpp import CppStrategy
from .generic import GenericStrategy
from .go import GoStrategy
from .java import JavaStrategy
from .javascript import JavascriptStrategy
from .python import PythonStrategy
from .registry import LanguageRegistry
from .ruby import RubyStrategy

__all__ = [
    "LanguageStrategy",
    "LanguageRegistry",
    "GenericStrategy",
    "PythonStrategy",
    "JavaStrategy",
    "RubyStrategy",
    "JavascriptStrategy",
    "GoStrategy",
    "CppStrategy",
]
