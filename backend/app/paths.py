"""
Centralized path definitions for data storage.

All paths are relative to settings.DATA_DIR as the root.
This module ensures directories exist when the module is imported.
"""

import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Base data directory (absolute)
DATA_DIR = Path(settings.DATA_DIR).resolve()

# Repository clones (bare repos)
REPOS_DIR = DATA_DIR / "repos"

# Git worktrees for filesystem access to specific commits
WORKTREES_DIR = DATA_DIR / "worktrees"

# CI/CD build logs downloaded from providers
LOGS_DIR = DATA_DIR / "logs"

# Hamilton pipeline cache directory
HAMILTON_CACHE_DIR = DATA_DIR / "hamilton_cache"


def ensure_data_dirs() -> None:
    """Create all required data directories if they don't exist."""
    for d in [DATA_DIR, REPOS_DIR, WORKTREES_DIR, LOGS_DIR, HAMILTON_CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Path Helper Functions
# =============================================================================


def get_repo_path(github_repo_id: int) -> Path:
    """Get bare repo path for a repository by its GitHub ID."""
    return REPOS_DIR / str(github_repo_id)


def get_worktrees_path(github_repo_id: int) -> Path:
    """Get worktrees base path for a repository by its GitHub ID."""
    return WORKTREES_DIR / str(github_repo_id)


def get_worktree_path(github_repo_id: int, commit_sha: str) -> Path:
    """Get specific worktree path for a commit."""
    return WORKTREES_DIR / str(github_repo_id) / commit_sha[:12]


def get_logs_path(github_repo_id: int) -> Path:
    """Get logs base path for a repository by its GitHub ID."""
    return LOGS_DIR / str(github_repo_id)


def get_build_logs_path(github_repo_id: int, build_id: str) -> Path:
    """Get specific build logs path."""
    return LOGS_DIR / str(github_repo_id) / build_id


# Auto-create directories on import
ensure_data_dirs()
