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
from .registry import LanguageRegistry
from .generic import GenericStrategy
from .python import PythonStrategy
from .java import JavaStrategy
from .ruby import RubyStrategy
from .javascript import JavascriptStrategy
from .go import GoStrategy
from .cpp import CppStrategy

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
