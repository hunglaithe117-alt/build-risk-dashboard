from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from app.ci_providers.models import CIProvider

from .base import BaseEntity


class Provider(str, Enum):
    GITHUB = "github"


class TestFramework(str, Enum):
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


class ImportStatus(str, Enum):
    QUEUED = "queued"
    IMPORTING = "importing"
    IMPORTED = "imported"
    FAILED = "failed"


class SyncStatus(str, Enum):
    """Repository sync status."""

    SUCCESS = "success"
    FAILED = "failed"


class EnrichmentImportStatus(str, Enum):
    PENDING = "pending"
    IMPORTED = "imported"
    FAILED = "failed"


class RepoValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    ERROR = "error"


class BaseRepositoryEntity(BaseEntity):
    """Common fields shared by repository entities."""

    model_config = ConfigDict(use_enum_values=True)

    full_name: str  # e.g., "owner/repo"
    github_repo_id: Optional[int] = None
    default_branch: Optional[str] = "main"
    is_private: bool = False
    main_lang: Optional[str] = None
    source_languages: List[str] = Field(default_factory=list)
    test_frameworks: List[TestFramework] = Field(default_factory=list)
    ci_provider: CIProvider = CIProvider.GITHUB_ACTIONS
    installation_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
