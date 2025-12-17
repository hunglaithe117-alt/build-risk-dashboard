"""
Centralized path definitions for data storage.

All paths are relative to settings.DATA_DIR as the root.
This module ensures directories exist when the module is imported.
"""

from pathlib import Path

from app.config import settings

# Base data directory (absolute)
DATA_DIR = Path(settings.DATA_DIR).resolve()

# Repository clones (bare repos)
REPOS_DIR = DATA_DIR / "repos"

# Git worktrees for filesystem access to specific commits
WORKTREES_DIR = DATA_DIR / "worktrees"

# CI/CD build logs downloaded from providers
LOGS_DIR = DATA_DIR / "logs"

# Artifacts from analysis tools (e.g., SonarQube reports)
ARTIFACTS_DIR = DATA_DIR / "artifacts"

# SonarQube scanner work directory (repos and worktrees for scans)
SONAR_WORK_DIR = DATA_DIR / "sonar-work"


def ensure_data_dirs() -> None:
    """Create all required data directories if they don't exist."""
    for d in [DATA_DIR, REPOS_DIR, WORKTREES_DIR, LOGS_DIR, ARTIFACTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# Auto-create directories on import
ensure_data_dirs()
