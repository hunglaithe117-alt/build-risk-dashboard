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
from backend.app.entities.raw_build_run import RawWorkflowRun
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
class WorkflowRunInput:
    """Workflow run data."""

    workflow_run_id: int
    run_number: int
    head_sha: str
    conclusion: Optional[str]
    ci_created_at: Optional[datetime]
    ci_updated_at: Optional[datetime]
    raw_payload: Dict[str, Any]

    @classmethod
    def from_entity(cls, workflow_run: RawWorkflowRun) -> WorkflowRunInput:
        """Create from WorkflowRunRaw entity."""
        return cls(
            workflow_run_id=workflow_run.workflow_run_id,
            run_number=workflow_run.build_number,
            head_sha=workflow_run.head_sha,
            conclusion=workflow_run.conclusion,
            ci_created_at=workflow_run.build_created_at,
            ci_updated_at=workflow_run.build_updated_at,
            raw_payload=workflow_run.github_metadata or {},
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
class HamiltonInputs:
    """Container for all Hamilton pipeline inputs."""

    git_history: GitHistoryInput
    git_worktree: GitWorktreeInput
    repo: RepoInput
    workflow_run: WorkflowRunInput
    repo_config: RepoConfigInput
    is_commit_available: bool
    effective_sha: Optional[str] = None


def build_hamilton_inputs(
    raw_repo: RawRepository,
    repo_config: RepoConfigBase,
    workflow_run: RawWorkflowRun,
    repo_path: Path,
    github_client: Optional[Any] = None,
    worktrees_base: Optional[Path] = None,
) -> HamiltonInputs:
    """
    Build all Hamilton input objects from entities.

    Always handles missing fork commits by attempting to replay them using
    the commit_replay service. If github_client is not provided, uses
    public GitHub client.

    Args:
        raw_repo: RawRepository entity from DB
        repo_config: ModelRepoConfig or DatasetRepoConfig entity
        workflow_run: RawWorkflowRun entity
        repo_path: Path to the git repository (bare repo)
        github_client: Optional GitHubClient (uses public client if not provided)
        worktrees_base: Optional base path for worktrees (default: repo_path/../worktrees)

    Returns:
        HamiltonInputs containing all input objects
    """
    import subprocess
    import logging

    logger = logging.getLogger(__name__)

    original_sha = workflow_run.head_sha
    effective_sha: Optional[str] = None
    is_commit_available = False
    worktree_path: Optional[Path] = None

    # Check commit availability
    if repo_path.exists():
        try:
            subprocess.run(
                ["git", "cat-file", "-e", original_sha],
                cwd=str(repo_path),
                check=True,
                capture_output=True,
                timeout=10,
            )
            is_commit_available = True
            effective_sha = original_sha
        except subprocess.CalledProcessError:
            # Commit not found locally - attempt to replay
            logger.info(
                f"Commit {original_sha[:8]} not found locally. "
                f"Attempting to replay fork commit..."
            )

            # Get github client if not provided
            client = github_client
            if not client:
                try:
                    from app.services.github.github_client import (
                        get_public_github_client,
                    )

                    client = get_public_github_client()
                except Exception as e:
                    logger.warning(f"Failed to get public GitHub client: {e}")

            if client:
                try:
                    from app.services.commit_replay import ensure_commit_exists

                    synthetic_sha = ensure_commit_exists(
                        repo_path=repo_path,
                        commit_sha=original_sha,
                        repo_slug=raw_repo.full_name,
                        github_client=client,
                    )
                    if synthetic_sha:
                        effective_sha = synthetic_sha
                        is_commit_available = True
                        logger.info(
                            f"Replayed fork commit. Using synthetic SHA: {synthetic_sha[:8]}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to replay fork commit: {e}")

    # Setup worktree if commit is available and worktrees_base is provided
    if is_commit_available and effective_sha and worktrees_base:
        worktree_path = worktrees_base / effective_sha[:12]
        if not worktree_path.exists():
            try:
                # Prune stale worktrees first
                subprocess.run(
                    ["git", "worktree", "prune"],
                    cwd=str(repo_path),
                    capture_output=True,
                    check=False,
                )
                # Create worktree
                subprocess.run(
                    [
                        "git",
                        "worktree",
                        "add",
                        "--detach",
                        str(worktree_path),
                        effective_sha,
                    ],
                    cwd=str(repo_path),
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                logger.info(f"Created worktree at {worktree_path}")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to create worktree: {e}")
                worktree_path = None

    # Create GitHistoryInput
    git_history = GitHistoryInput(
        path=repo_path,
        effective_sha=effective_sha,
        original_sha=original_sha,
        is_commit_available=is_commit_available,
    )

    # Create GitWorktreeInput
    git_worktree = GitWorktreeInput(
        worktree_path=worktree_path,
        effective_sha=effective_sha,
        is_ready=worktree_path is not None and worktree_path.exists(),
    )

    # Create input objects from entities
    repo_input = RepoInput.from_entity(raw_repo)
    config_input = RepoConfigInput.from_entity(repo_config)
    workflow_input = WorkflowRunInput.from_entity(workflow_run)

    return HamiltonInputs(
        git_history=git_history,
        git_worktree=git_worktree,
        repo=repo_input,
        workflow_run=workflow_input,
        repo_config=config_input,
        is_commit_available=is_commit_available,
        effective_sha=effective_sha,
    )
