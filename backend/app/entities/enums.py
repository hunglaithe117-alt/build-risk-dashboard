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
    RSPEC = "rspec"
    MINITEST = "minitest"
    TESTUNIT = "testunit"
    CUCUMBER = "cucumber"
    # Java
    JUNIT = "junit"
    TESTNG = "testng"
    # JavaScript/TypeScript
    JEST = "jest"
    MOCHA = "mocha"
    JASMINE = "jasmine"
    VITEST = "vitest"
    # Go
    GOTEST = "gotest"
    GOTESTSUM = "gotestsum"
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


class ModelImportStatus(str, Enum):
    """Status of the model repository import process."""

    QUEUED = "queued"
    IMPORTING = "importing"
    IMPORTED = "imported"
    FAILED = "failed"
    PAUSED = "paused"


class ModelSyncStatus(str, Enum):
    """Status of the last sync operation."""

    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class DatasetRepoValidationStatus(str, Enum):
    """Validation status for a repository in the dataset."""

    PENDING = "pending"
    VALIDATING = "validating"
    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    ERROR = "error"


class WorkflowRunStatus(str, Enum):
    """GitHub Actions workflow run status."""

    QUEUED = "queued"
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PENDING = "pending"
    REQUESTED = "requested"
    UNKNOWN = "unknown"


class WorkflowConclusion(str, Enum):
    """GitHub Actions workflow run conclusion."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    NEUTRAL = "neutral"
    STALE = "stale"
    UNKNOWN = "unknown"


class ModelBuildConclusion(str, Enum):
    """Conclusion status for model training builds."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
