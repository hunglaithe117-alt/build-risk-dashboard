"""
Base inputs for Hamilton DAG.

These dataclasses represent the resources that feature functions depend on.
They are passed directly to driver.execute(inputs={...}).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.entities.raw_repository import RawRepository
from app.entities.raw_build_run import RawBuildRun
from app.entities.repo_config_base import RepoConfigBase


@dataclass
class GitHistoryInput:
    """Git history access - bare repo for commit operations (no worktree)."""

    path: Path
    effective_sha: Optional[str]
    original_sha: str
    is_commit_available: bool

    @classmethod
    def from_handle(cls, handle: Any) -> GitHistoryInput:
        """Create from existing GitHistoryHandle."""
        return cls(
            path=handle.path,
            effective_sha=handle.effective_sha,
            original_sha=handle.original_sha,
            is_commit_available=handle.is_commit_available,
        )


@dataclass
class GitWorktreeInput:
    """Git worktree for filesystem operations on a specific commit."""

    worktree_path: Optional[Path]
    effective_sha: Optional[str]
    is_ready: bool

    @classmethod
    def from_handle(cls, handle: Any) -> GitWorktreeInput:
        """Create from existing GitWorktreeHandle."""
        return cls(
            worktree_path=handle.worktree_path,
            effective_sha=handle.effective_sha,
            is_ready=handle.is_ready,
        )


@dataclass
class RepoInput:
    """Repository metadata from RawRepository (fetched from DB by repo_id)."""

    id: str
    full_name: str
    main_lang: Optional[str]
    source_languages: List[str]
    is_private: bool
    github_repo_id: Optional[int]
    default_branch: str
    language_stats: Dict[str, int]

    @classmethod
    def from_entity(cls, repo: RawRepository) -> RepoInput:
        """Create from RawRepository entity."""
        return cls(
            id=str(repo.id),
            full_name=repo.full_name,
            main_lang=repo.main_lang,
            source_languages=repo.source_languages or [],
            is_private=repo.is_private,
            github_repo_id=repo.github_repo_id,
            default_branch=repo.default_branch,
            language_stats=repo.language_stats or {},
        )


@dataclass
class RepoConfigInput:
    """User-configurable repository settings from RepoConfigBase."""

    id: str
    ci_provider: str
    source_languages: List[str]
    test_frameworks: List[str]

    @classmethod
    def from_entity(cls, config: RepoConfigBase) -> RepoConfigInput:
        """Create from ModelRepoConfig or DatasetRepoConfig entity."""
        return cls(
            id=str(config.id),
            ci_provider=(
                str(config.ci_provider.value)
                if config.ci_provider
                else "github_actions"
            ),
            source_languages=config.source_languages or [],
            test_frameworks=[str(tf.value) for tf in (config.test_frameworks or [])],
        )


@dataclass
class BuildRunInput:
    """Build run data from any CI provider."""

    build_id: str
    build_number: Optional[int]
    commit_sha: str
    conclusion: Optional[str]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    raw_data: Dict[str, Any]

    @classmethod
    def from_entity(cls, build_run: RawBuildRun) -> BuildRunInput:
        """Create from RawBuildRun entity."""
        return cls(
            build_id=build_run.build_id,
            build_number=build_run.build_number,
            commit_sha=build_run.commit_sha,
            conclusion=(
                str(build_run.conclusion.value) if build_run.conclusion else None
            ),
            created_at=build_run.created_at,
            completed_at=build_run.completed_at,
            duration_seconds=build_run.duration_seconds,
            raw_data=build_run.raw_data or {},
        )


@dataclass
class GitHubClientInput:
    """GitHub API client wrapper."""

    client: Any  # GitHubClient instance
    full_name: str

    @classmethod
    def from_handle(cls, handle: Any, full_name: str) -> GitHubClientInput:
        """Create from GitHubClientHandle."""
        return cls(client=handle.client, full_name=full_name)


@dataclass
class BuildLogsInput:
    """Build job logs from CI provider."""

    logs_dir: Optional[Path]  # Directory containing log files
    log_files: List[str]  # List of log file paths
    is_available: bool  # Whether logs were downloaded successfully

    @classmethod
    def from_path(cls, logs_dir: Optional[Path]) -> BuildLogsInput:
        """Create from logs directory path."""
        if logs_dir and logs_dir.exists():
            log_files = [str(f) for f in logs_dir.glob("*.log")]
            return cls(
                logs_dir=logs_dir,
                log_files=log_files,
                is_available=len(log_files) > 0,
            )
        return cls(logs_dir=None, log_files=[], is_available=False)


@dataclass
class HamiltonInputs:
    """Container for all Hamilton pipeline inputs."""

    git_history: GitHistoryInput
    git_worktree: GitWorktreeInput
    repo: RepoInput
    build_run: BuildRunInput
    repo_config: RepoConfigInput
    is_commit_available: bool
    effective_sha: Optional[str] = None


def build_hamilton_inputs(
    raw_repo: RawRepository,
    repo_config: RepoConfigBase,
    build_run: RawBuildRun,
    repo_path: Path,
    worktrees_base: Optional[Path] = None,
) -> HamiltonInputs:
    """
    Build all Hamilton input objects from entities.

    Uses effective_sha from DB if available (set during ingestion for fork commits).

    Args:
        raw_repo: RawRepository entity from DB
        repo_config: ModelRepoConfig or DatasetRepoConfig entity
        build_run: RawBuildRun entity (with effective_sha if fork was replayed)
        repo_path: Path to the git repository (bare repo)
        worktrees_base: Optional base path for worktrees

    Returns:
        HamiltonInputs containing all input objects
    """
    import subprocess
    import logging

    logger = logging.getLogger(__name__)

    original_sha = build_run.commit_sha
    # Use effective_sha from DB if set (fork commits replayed during ingestion)
    effective_sha = build_run.effective_sha or original_sha
    is_commit_available = False
    worktree_path: Optional[Path] = None

    # Check commit availability using effective_sha
    if repo_path.exists():
        try:
            subprocess.run(
                ["git", "cat-file", "-e", effective_sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=10,
            )
            is_commit_available = True
        except subprocess.CalledProcessError:
            logger.warning(f"Commit {effective_sha[:8]} not found in repo")

    # Use pre-created worktree from ingestion
    if is_commit_available and worktrees_base:
        worktree_path = worktrees_base / effective_sha[:12]
        if not worktree_path.exists():
            worktree_path = None

    # Create GitHistoryInput
    git_history = GitHistoryInput(
        path=repo_path,
        effective_sha=effective_sha if is_commit_available else None,
        original_sha=original_sha,
        is_commit_available=is_commit_available,
    )

    # Create GitWorktreeInput
    git_worktree = GitWorktreeInput(
        worktree_path=worktree_path,
        effective_sha=effective_sha if is_commit_available else None,
        is_ready=worktree_path is not None and worktree_path.exists(),
    )

    # Create input objects from entities
    repo_input = RepoInput.from_entity(raw_repo)
    config_input = RepoConfigInput.from_entity(repo_config)
    build_run_input = BuildRunInput.from_entity(build_run)

    return HamiltonInputs(
        git_history=git_history,
        git_worktree=git_worktree,
        repo=repo_input,
        build_run=build_run_input,
        repo_config=config_input,
        is_commit_available=is_commit_available,
        effective_sha=effective_sha if is_commit_available else None,
    )
