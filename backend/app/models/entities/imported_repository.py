"""Repository entity - represents a tracked repository"""

from typing import Optional
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

from .base import BaseEntity, PyObjectId


class Provider(str, Enum):

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"


class TestFramework(str, Enum):

    PYTEST = "pytest"
    UNITTEST = "unittest"
    RSPEC = "rspec"
    MINITEST = "minitest"
    TESTUNIT = "testunit"
    CUCUMBER = "cucumber"
    JUNIT = "junit"
    TESTNG = "testng"


class SourceLanguage(str, Enum):

    PYTHON = "python"
    RUBY = "ruby"
    JAVA = "java"


class CIProvider(str, Enum):

    GITHUB_ACTIONS = "github_actions"
    TRAVIS_CI = "travis_ci"


class ImportStatus(str, Enum):

    QUEUED = "queued"
    IMPORTING = "importing"
    IMPORTED = "imported"
    FAILED = "failed"


class ImportSource(str, Enum):
    """Source of repository import."""
    MAIN = "main"          # Imported via main flow (/repos) - only once
    DATASET = "dataset"    # Imported via dataset builder - can be reused


class ImportedRepository(BaseEntity):
    user_id: PyObjectId | None = None
    provider: Provider = Provider.GITHUB

    full_name: str  # "owner/repo"
    github_repo_id: int | None = None
    default_branch: str | None = None
    is_private: bool = False
    main_lang: str | None = None

    test_frameworks: List[TestFramework] = []
    source_languages: List[SourceLanguage] = []

    ci_provider: CIProvider = CIProvider.GITHUB_ACTIONS
    installation_id: str | None = None

    import_status: ImportStatus = ImportStatus.QUEUED
    total_builds_imported: int = 0
    last_scanned_at: datetime | None = None
    last_sync_error: str | None = None
    notes: str | None = None

    # Lazy Sync Fields
    last_synced_at: Optional[datetime] = None

    # SonarQube Configuration
    sonar_config: Optional[str] = None  # Content of sonar-project.properties
    last_sync_status: str | None = None  # "success", "failed"
    last_remote_check_at: datetime | None = None
    latest_synced_run_created_at: datetime | None = None

    # Import Source - distinguishes main flow vs dataset builder imports
    import_source: ImportSource = ImportSource.MAIN

    # Metadata
    metadata: Dict[str, Any] = {}
