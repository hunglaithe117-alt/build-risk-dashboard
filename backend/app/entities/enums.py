"""
Shared enums for entities.

This module contains enums that are used across multiple entity files.
"""

from enum import Enum


class TestFramework(str, Enum):
    """Supported test frameworks for log parsing."""

    # Python
    PYTEST = "pytest"
    UNITTEST = "unittest"
    # Ruby

    TESTUNIT = "testunit"
    CUCUMBER = "cucumber"
    # Java
    JUNIT = "junit"
    TESTNG = "testng"
    # JavaScript/TypeScript
    JEST = "jest"
    MOCHA = "mocha"
    JASMINE = "jasmine"

    # Go
    GOTEST = "gotest"

    # C/C++
    GTEST = "gtest"
    CATCH2 = "catch2"
    CTEST = "ctest"


class ExtractionStatus(str, Enum):
    """Feature extraction status for builds."""

    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
