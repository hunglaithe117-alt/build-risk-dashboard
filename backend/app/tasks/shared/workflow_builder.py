"""
Shared Workflow Builder - Build Celery workflows from task levels.

This module provides helpers to build Celery chain/group workflows
based on task levels from resource_dag.

IMPORTANT: For worktrees and logs, we build the FULL chunk signatures directly
(not calling orchestrator tasks) so Celery can properly chain with processing.
"""

import logging
from typing import Dict, List, Optional

from celery import chain, chord, group
from celery.canvas import Signature

from app.config import settings
from app.tasks.shared.ingestion_tasks import (
    aggregate_logs_results,
    clone_repo,
    create_worktree_chunk,
    download_logs_chunk,
)

logger = logging.getLogger(__name__)


def build_ingestion_workflow(
    tasks_by_level: Dict[int, List[str]],
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    build_ids: List[str],
    commit_shas: List[str],
    ci_provider: str,
    correlation_id: Optional[str] = None,
) -> Optional[Signature]:
    """
    Build a Celery workflow from task levels.

    Tasks at the same level run in parallel (group).
    Different levels run sequentially (chain).

    IMPORTANT: This builds the COMPLETE workflow including chunk tasks,
    so the entire workflow can be chained with processing tasks.

    Args:
        tasks_by_level: Dict mapping level number to list of task names
        raw_repo_id: MongoDB ID of raw repo
        github_repo_id: GitHub's internal repository ID for paths
        full_name: Repository full name (owner/repo)
        build_ids: List of build IDs for log download
        commit_shas: Optional list of commit SHAs for worktree creation
        ci_provider: CI provider string (e.g., "github_actions")
        correlation_id: Optional correlation ID for tracing workflow execution

    Returns:
        Celery workflow (chain/group/chord) or None if no tasks
    """
    from uuid import uuid4

    # Generate correlation_id if not provided
    if not correlation_id:
        correlation_id = str(uuid4())

    if not tasks_by_level:
        return None

    level_workflows = []

    for level in sorted(tasks_by_level.keys()):
        task_names = tasks_by_level[level]
        level_tasks = []

        for task_name in task_names:
            task_sig = _create_task_signature(
                task_name=task_name,
                raw_repo_id=raw_repo_id,
                github_repo_id=github_repo_id,
                full_name=full_name,
                build_ids=build_ids,
                commit_shas=commit_shas,
                ci_provider=ci_provider,
                correlation_id=correlation_id,
            )
            if task_sig:
                level_tasks.append(task_sig)

        if not level_tasks:
            continue

        if len(level_tasks) == 1:
            level_workflows.append(level_tasks[0])
        else:
            # Multiple tasks at same level - run in parallel
            level_workflows.append(group(*level_tasks))

    if not level_workflows:
        return None

    # Chain all levels together
    if len(level_workflows) == 1:
        return level_workflows[0]
    return chain(*level_workflows)


def _create_task_signature(
    task_name: str,
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    build_ids: List[str],
    commit_shas: List[str],
    ci_provider: str,
    correlation_id: Optional[str] = None,
) -> Optional[Signature]:
    """
    Create a Celery task signature for a given task name.

    For worktrees: Returns a CHAIN of chunk tasks (sequential).
    For logs: Returns a CHORD of chunk tasks (parallel) with aggregate callback.
    """
    if task_name == "clone_repo":
        return clone_repo.si(
            raw_repo_id=raw_repo_id,
            github_repo_id=github_repo_id,
            full_name=full_name,
            correlation_id=correlation_id,
        )

    elif task_name == "create_worktrees":
        return _build_worktree_chain(
            raw_repo_id=raw_repo_id,
            github_repo_id=github_repo_id,
            commit_shas=commit_shas,
            correlation_id=correlation_id,
        )

    elif task_name == "download_build_logs":
        return _build_logs_chord(
            raw_repo_id=raw_repo_id,
            github_repo_id=github_repo_id,
            full_name=full_name,
            build_ids=build_ids,
            ci_provider=ci_provider,
            correlation_id=correlation_id,
        )

    else:
        logger.warning(f"Unknown task name: {task_name}")
        return None


def _build_worktree_chain(
    raw_repo_id: str,
    github_repo_id: int,
    commit_shas: List[str],
    correlation_id: Optional[str] = None,
) -> Optional[Signature]:
    """
    Build a chain of worktree chunk tasks for sequential execution.

    Returns None if no commit SHAs provided.
    """
    if not commit_shas:
        return None

    # Deduplicate
    unique_shas = list(dict.fromkeys(commit_shas))

    chunk_size = settings.INGESTION_WORKTREES_PER_CHUNK
    chunks = [unique_shas[i : i + chunk_size] for i in range(0, len(unique_shas), chunk_size)]
    total_chunks = len(chunks)

    logger.info(
        f"[corr={correlation_id[:8] if correlation_id else 'none'}] "
        f"Building worktree chain for github_repo_id={github_repo_id}: "
        f"{len(unique_shas)} commits in {total_chunks} chunks"
    )

    # Build chain of chunk tasks
    chunk_signatures = []
    for idx, chunk_shas in enumerate(chunks):
        sig = create_worktree_chunk.si(
            raw_repo_id=raw_repo_id,
            github_repo_id=github_repo_id,
            commit_shas=chunk_shas,
            chunk_index=idx,
            total_chunks=total_chunks,
            correlation_id=correlation_id,
        )
        chunk_signatures.append(sig)

    return chain(*chunk_signatures)


def _build_logs_chord(
    raw_repo_id: str,
    github_repo_id: int,
    full_name: str,
    build_ids: List[str],
    ci_provider: str,
    correlation_id: Optional[str] = None,
) -> Optional[Signature]:
    """
    Build a chord of log download chunk tasks for parallel execution.

    Returns None if no build IDs provided.
    """
    if not build_ids:
        return None

    # Deduplicate
    unique_build_ids = list(dict.fromkeys(build_ids))
    chunk_size = settings.INGESTION_LOGS_PER_CHUNK
    chunks = [
        unique_build_ids[i : i + chunk_size] for i in range(0, len(unique_build_ids), chunk_size)
    ]
    total_chunks = len(chunks)

    logger.info(
        f"[corr={correlation_id[:8] if correlation_id else 'none'}] "
        f"Building logs chord for github_repo_id={github_repo_id}: "
        f"{len(unique_build_ids)} builds in {total_chunks} parallel chunks"
    )

    # Build chord: parallel chunk tasks → aggregate callback
    chunk_tasks = [
        download_logs_chunk.si(
            raw_repo_id=raw_repo_id,
            github_repo_id=github_repo_id,
            full_name=full_name,
            build_ids=chunk_ids,
            ci_provider=ci_provider,
            chunk_index=idx,
            total_chunks=total_chunks,
            correlation_id=correlation_id,
        )
        for idx, chunk_ids in enumerate(chunks)
    ]

    callback = aggregate_logs_results.s(
        raw_repo_id=raw_repo_id,
        github_repo_id=github_repo_id,
        total_chunks=total_chunks,
        correlation_id=correlation_id,
    )

    return chord(group(chunk_tasks), callback).set(chord_unlock_on_error=True)
