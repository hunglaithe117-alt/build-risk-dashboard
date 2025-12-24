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

from app.entities.raw_build_run import RawBuildRun
from app.entities.raw_repository import RawRepository


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
    is_private: bool
    github_repo_id: Optional[int]
    default_branch: str

    @classmethod
    def from_entity(cls, repo: RawRepository) -> RepoInput:
        """Create from RawRepository entity."""
        return cls(
            id=str(repo.id),
            full_name=repo.full_name,
            main_lang=repo.main_lang,
            is_private=repo.is_private,
            github_repo_id=repo.github_repo_id,
            default_branch=repo.default_branch,
        )


@dataclass
class FeatureConfigInput:
    """
    Dynamic feature configuration from user selections.

    Supports multi-scope configs:
    - Global configs: Applied to all builds (e.g., lookback_days)
    - Repo configs: Applied per-repository (e.g., source_languages)

    Structure:
        {
            "lookback_days": 60,  # global config
            "repos": {  # repo-specific configs
                "owner/repo1": {
                    "source_languages": ["python"],
                    "test_frameworks": ["pytest"]
                }
            }
        }
    """

    id: str
    feature_configs: Dict[str, Any]
    current_repo: Optional[str] = None  # Repository context for scope lookup

    def get(self, key: str, default: Any = None, scope: str = "auto") -> Any:
        """
        Get config value with scope awareness.

        Args:
            key: Config field name
            default: Default value if not found
            scope: "global", "repo", or "auto" (checks repo first, then global)

        Returns:
            Config value from appropriate scope
        """
        # For repo scope or auto, try repo-specific config first
        if scope in ("repo", "auto"):
            if self.current_repo and "repos" in self.feature_configs:
                repo_configs = self.feature_configs["repos"].get(self.current_repo, {})
                if key in repo_configs:
                    return repo_configs[key]

        # For global scope or auto (fallback), check global level
        if scope in ("global", "auto"):
            if key in self.feature_configs and key != "repos":
                return self.feature_configs[key]

        return default

    @classmethod
    def from_entity(cls, config: Any, current_repo: Optional[str] = None) -> FeatureConfigInput:
        """
        Create from ModelRepoConfig, DatasetVersion entity, or direct feature_configs dict.

        Args:
            config: Entity with feature_configs field, OR feature_configs dict directly
            current_repo: Optional repo full_name for repo-scoped lookups
        """
        # Support direct dict input (for simpler API)
        if isinstance(config, dict):
            return cls(
                id="direct",
                feature_configs=config,
                current_repo=current_repo,
            )

        # Entity input - extract feature_configs from entity
        return cls(
            id=str(getattr(config, "id", "unknown")),
            feature_configs=getattr(config, "feature_configs", {}) or {},
            current_repo=current_repo,
        )

    @classmethod
    def from_dict(
        cls, feature_configs: Dict[str, Any], current_repo: Optional[str] = None
    ) -> FeatureConfigInput:
        """
        Create directly from feature_configs dict.

        Args:
            feature_configs: The configuration dict
            current_repo: Optional repo full_name for repo-scoped lookups
        """
        return cls(
            id="dict",
            feature_configs=feature_configs or {},
            current_repo=current_repo,
        )


@dataclass
class BuildRunInput:
    """Build run data from any CI provider."""

    ci_run_id: str
    build_number: Optional[int]
    commit_sha: str
    conclusion: Optional[str]
    created_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    raw_data: Dict[str, Any]
    ci_provider: str

    @classmethod
    def from_entity(cls, build_run: RawBuildRun) -> BuildRunInput:
        """Create from RawBuildRun entity."""
        # Handle conclusion - can be enum or string (due to use_enum_values=True)
        conclusion_value = build_run.conclusion
        if hasattr(conclusion_value, "value"):
            conclusion_value = conclusion_value.value
        conclusion_str = str(conclusion_value) if conclusion_value else None

        return cls(
            ci_run_id=build_run.ci_run_id,
            build_number=build_run.build_number,
            commit_sha=build_run.commit_sha,
            conclusion=conclusion_str,
            created_at=build_run.created_at,
            completed_at=build_run.completed_at,
            duration_seconds=build_run.duration_seconds,
            raw_data=build_run.raw_data or {},
            ci_provider=build_run.provider.value,
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
    feature_config: FeatureConfigInput
    build_logs: BuildLogsInput
    is_commit_available: bool
    effective_sha: Optional[str] = None


def build_hamilton_inputs(
    raw_repo: RawRepository,
    feature_config: Dict[str, Any],
    build_run: RawBuildRun,
    repo_path: Path,
    worktrees_base: Optional[Path] = None,
    logs_base: Optional[Path] = None,
) -> HamiltonInputs:
    """
    Build all Hamilton input objects from entities.

    Consolidates ALL input construction in one place for consistency.

    Args:
        raw_repo: RawRepository entity from DB
        feature_config: Feature configuration dict
        build_run: RawBuildRun entity (with effective_sha if fork was replayed)
        repo_path: Path to the git repository (bare repo)
        worktrees_base: Optional base path for worktrees
        logs_base: Optional base path for build logs (LOGS_DIR)

    Returns:
        HamiltonInputs containing all input objects
    """
    import logging
    import subprocess

    logger = logging.getLogger(__name__)

    original_sha = build_run.commit_sha
    # Use effective_sha from DB if set (fork commits replayed during ingestion)
    effective_sha = build_run.effective_sha or original_sha
    is_commit_available = False
    worktree_path: Optional[Path] = None

    # Check repo path exists
    if not repo_path.exists():
        logger.warning(f"Repo path not found: {repo_path}")
    else:
        # Check commit availability using effective_sha
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
            logger.warning(f"Commit {effective_sha[:8]} not found in repo {raw_repo.full_name}")

    # Check worktree availability - try effective_sha first, then original_sha
    if is_commit_available and worktrees_base:
        # Try effective_sha (used when fork was replayed)
        worktree_path = worktrees_base / effective_sha[:12]
        if not worktree_path.exists():
            # Fallback: try original_sha (normal case, or worktree created before replay)
            original_worktree_path = worktrees_base / original_sha[:12]
            if original_worktree_path.exists():
                worktree_path = original_worktree_path
            else:
                logger.warning(
                    f"Worktree not found: tried {effective_sha[:12]} and {original_sha[:12]}"
                )
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
    # Pass current_repo for repo-scoped config lookup
    config_input = FeatureConfigInput.from_entity(feature_config, current_repo=raw_repo.full_name)
    build_run_input = BuildRunInput.from_entity(build_run)

    # Create BuildLogsInput
    logs_dir: Optional[Path] = None
    if build_run.logs_path:
        logs_dir = Path(build_run.logs_path)
    elif logs_base:
        logs_dir = logs_base / str(raw_repo.github_repo_id) / str(build_run.ci_run_id)
    build_logs = BuildLogsInput.from_path(logs_dir)

    # Log warnings for unavailable inputs
    if not is_commit_available:
        logger.warning(f"[INPUT] git_history unavailable for commit {original_sha[:8]}")
    if not git_worktree.is_ready:
        logger.warning(f"[INPUT] git_worktree not ready for commit {original_sha[:8]}")
    if not build_logs.is_available:
        logger.warning(f"[INPUT] build_logs not found at {logs_dir}")

    return HamiltonInputs(
        git_history=git_history,
        git_worktree=git_worktree,
        repo=repo_input,
        build_run=build_run_input,
        feature_config=config_input,
        build_logs=build_logs,
        is_commit_available=is_commit_available,
        effective_sha=effective_sha if is_commit_available else None,
    )
