from .build_log import BUILD_LOG_METADATA
from .git import GIT_METADATA
from .github import GITHUB_METADATA
from .repo import REPO_METADATA
from .sonar import SONAR_METADATA, SONAR_KEY_TO_FEATURE, get_sonar_metric_keys

ALL_FEATURE_METADATA = {
    **BUILD_LOG_METADATA,
    **GIT_METADATA,
    **GITHUB_METADATA,
    **REPO_METADATA,
    **SONAR_METADATA,
}

__all__ = [
    "BUILD_LOG_METADATA",
    "GIT_METADATA",
    "GITHUB_METADATA",
    "REPO_METADATA",
    "SONAR_METADATA",
    "SONAR_KEY_TO_FEATURE",
    "get_sonar_metric_keys",
    "ALL_FEATURE_METADATA",
]
