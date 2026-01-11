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

# Scan configuration files (SonarQube/Trivy per-version per-repo)
SCAN_CONFIG_DIR = DATA_DIR / "scan-config"

# Export job output files (CSV, JSON exports)
EXPORTS_DIR = DATA_DIR / "exports"

# Training Scenario configs (YAML files uploaded by users)
TRAINING_SCENARIOS_DIR = DATA_DIR / "training_scenarios"

# Training Dataset splits (generated parquet/csv files)
TRAINING_DATASETS_DIR = DATA_DIR / "training_datasets"


def ensure_data_dirs() -> None:
    """Create all required data directories if they don't exist."""
    for d in [
        DATA_DIR,
        REPOS_DIR,
        WORKTREES_DIR,
        LOGS_DIR,
        HAMILTON_CACHE_DIR,
        SCAN_CONFIG_DIR,
        EXPORTS_DIR,
        TRAINING_SCENARIOS_DIR,
        TRAINING_DATASETS_DIR,
    ]:
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


def get_sonarqube_config_dir(version_id: str, github_repo_id: int) -> Path:
    """
    Get SonarQube config directory for a version/repo.

    Structure: scan-config/sonarqube/{version_id}/{github_repo_id}/
    """
    return SCAN_CONFIG_DIR / "sonarqube" / version_id / str(github_repo_id)


def get_sonarqube_config_path(version_id: str, github_repo_id: int) -> Path:
    """
    Get sonar-project.properties file path for a version/repo.

    Structure: scan-config/sonarqube/{version_id}/{github_repo_id}/sonar-project.properties
    """
    return (
        get_sonarqube_config_dir(version_id, github_repo_id)
        / "sonar-project.properties"
    )


def get_trivy_config_dir(version_id: str, github_repo_id: int) -> Path:
    """
    Get Trivy config directory for a version/repo.

    Structure: scan-config/trivy/{version_id}/{github_repo_id}/
    """
    return SCAN_CONFIG_DIR / "trivy" / version_id / str(github_repo_id)


def get_trivy_config_path(version_id: str, github_repo_id: int) -> Path:
    """
    Get trivy.yaml file path for a version/repo.

    Structure: scan-config/trivy/{version_id}/{github_repo_id}/trivy.yaml
    """
    return get_trivy_config_dir(version_id, github_repo_id) / "trivy.yaml"


# =============================================================================
# Training Scenario Path Helpers
# =============================================================================


def get_training_scenario_dir(scenario_id: str) -> Path:
    """Get directory for a scenario's config and metadata."""
    return TRAINING_SCENARIOS_DIR / scenario_id


def get_training_scenario_config_path(scenario_id: str) -> Path:
    """Get YAML config file path for a scenario."""
    return get_training_scenario_dir(scenario_id) / "config.yaml"


def get_training_dataset_dir(scenario_id: str) -> Path:
    """Get directory for a scenario's generated datasets."""
    return TRAINING_DATASETS_DIR / scenario_id


def get_training_dataset_split_path(
    scenario_id: str, split_type: str, format: str = "parquet"
) -> Path:
    """
    Get generated split file path.

    Args:
        scenario_id: TrainingScenario ID
        split_type: train | validation | test | fold_N
        format: parquet | csv | pickle

    Returns:
        Path like: training_datasets/{scenario_id}/train.parquet
    """
    return get_training_dataset_dir(scenario_id) / f"{split_type}.{format}"


def cleanup_training_scenario_files(scenario_id: str) -> None:
    """
    Delete all files for a scenario (cleanup on scenario delete).
    """
    import shutil

    # Cleanup config
    config_dir = get_training_scenario_dir(scenario_id)
    if config_dir.exists():
        shutil.rmtree(config_dir, ignore_errors=True)
        logger.info(f"Cleaned up training scenario config for {scenario_id}")

    # Cleanup datasets
    dataset_dir = get_training_dataset_dir(scenario_id)
    if dataset_dir.exists():
        shutil.rmtree(dataset_dir, ignore_errors=True)
        logger.info(f"Cleaned up training datasets for {scenario_id}")


def cleanup_version_scan_configs(version_id: str) -> None:
    """
    Delete all scan config files for a version (cleanup on version delete).
    """
    import shutil

    for tool in ["sonarqube", "trivy"]:
        version_config_dir = SCAN_CONFIG_DIR / tool / version_id
        if version_config_dir.exists():
            shutil.rmtree(version_config_dir, ignore_errors=True)
            logger.info(f"Cleaned up {tool} configs for version {version_id}")


# Auto-create directories on import
ensure_data_dirs()
