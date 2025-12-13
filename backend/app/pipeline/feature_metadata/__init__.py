from .build_log import BUILD_LOG_METADATA
from .git import GIT_METADATA
from .github import GITHUB_METADATA
from .repo import REPO_METADATA

# NOTE: SonarQube and Trivy metadata moved to app.integrations module

ALL_FEATURE_METADATA = {
    **BUILD_LOG_METADATA,
    **GIT_METADATA,
    **GITHUB_METADATA,
    **REPO_METADATA,
}

__all__ = [
    "BUILD_LOG_METADATA",
    "GIT_METADATA",
    "GITHUB_METADATA",
    "REPO_METADATA",
    "ALL_FEATURE_METADATA",
]
