"""
Shared Workflow Builder - Build Celery workflows from task levels.

This module provides helpers to build Celery chain/group workflows
based on task levels from resource_dag.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from celery import chain, group, Signature

from app.tasks.shared import clone_repo, create_worktrees, download_build_logs

logger = logging.getLogger(__name__)


def build_ingestion_workflow(
    tasks_by_level: Dict[int, List[str]],
    repo_id: str,
    full_name: str,
    build_ids: Optional[List[str]] = None,
    commit_shas: Optional[List[str]] = None,
    ci_provider: Optional[str] = None,
    installation_id: Optional[str] = None,
    publish_status: bool = False,
    enable_fork_replay: bool = True,
    final_task: Optional[Signature] = None,
    custom_tasks: Optional[Dict[str, Signature]] = None,
) -> Optional[Union[chain, group, Signature]]:
    """
    Build a Celery workflow from task levels.

    Tasks at the same level run in parallel (group).
    Different levels run sequentially (chain).

    Args:
        tasks_by_level: Dict mapping level number to list of task names
        repo_id: Repository ID
        full_name: Repository full name (owner/repo)
        build_ids: Optional list of build IDs for log download
        commit_shas: Optional list of commit SHAs for worktree creation
        ci_provider: CI provider string
        installation_id: Optional GitHub installation ID for private repos
        publish_status: Whether to publish status updates to Redis
        enable_fork_replay: Whether to enable fork commit replay
        final_task: Optional final task to append to the workflow
        custom_tasks: Optional dict of task_name -> Signature for custom tasks

    Returns:
        Celery workflow (chain/group) or None if no tasks
    """
    if not tasks_by_level:
        return None

    custom_tasks = custom_tasks or {}
    level_workflows = []

    for level in sorted(tasks_by_level.keys()):
        task_names = tasks_by_level[level]
        level_tasks = []

        for task_name in task_names:
            # Check for custom task first
            if task_name in custom_tasks:
                level_tasks.append(custom_tasks[task_name])
                continue

            task_sig = _create_task_signature(
                task_name=task_name,
                repo_id=repo_id,
                full_name=full_name,
                build_ids=build_ids,
                commit_shas=commit_shas,
                ci_provider=ci_provider,
                installation_id=installation_id,
                publish_status=publish_status,
                enable_fork_replay=enable_fork_replay,
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

    # Add final task if provided
    if final_task:
        level_workflows.append(final_task)

    # Chain all levels together
    if len(level_workflows) == 1:
        return level_workflows[0]
    return chain(*level_workflows)


def _create_task_signature(
    task_name: str,
    repo_id: str,
    full_name: str,
    build_ids: Optional[List[str]] = None,
    commit_shas: Optional[List[str]] = None,
    ci_provider: Optional[str] = None,
    installation_id: Optional[str] = None,
    publish_status: bool = False,
    enable_fork_replay: bool = True,
) -> Optional[Signature]:
    """
    Create a Celery task signature for a given task name.

    Returns None for unknown tasks or tasks that can't be created
    (e.g., create_worktrees without commit_shas).
    """
    if task_name == "clone_repo":
        return clone_repo.s(
            repo_id=repo_id,
            full_name=full_name,
            installation_id=installation_id,
            publish_status=publish_status,
        )

    elif task_name == "create_worktrees":
        if not commit_shas:
            # Will get commit_shas from prev_result["build_ids"]
            return create_worktrees.s(
                repo_id=repo_id,
                enable_fork_replay=enable_fork_replay,
                publish_status=publish_status,
            )
        return create_worktrees.s(
            repo_id=repo_id,
            commit_shas=commit_shas,
            enable_fork_replay=enable_fork_replay,
            publish_status=publish_status,
        )

    elif task_name == "download_build_logs":
        return download_build_logs.s(
            repo_id=repo_id,
            full_name=full_name,
            build_ids=build_ids,
            ci_provider=ci_provider,
            installation_id=installation_id,
            publish_status=publish_status,
        )

    else:
        logger.warning(f"Unknown task name: {task_name}")
        return None
