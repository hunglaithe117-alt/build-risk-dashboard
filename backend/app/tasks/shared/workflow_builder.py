"""
Shared Workflow Builder - Build Celery workflows from task levels.

This module provides helpers to build Celery chain/group workflows
based on task levels from resource_dag.
"""

import logging
from typing import Dict, List, Optional

from celery import chain, group
from celery.canvas import Signature

from app.tasks.shared import clone_repo, create_worktrees, download_build_logs

logger = logging.getLogger(__name__)


def build_ingestion_workflow(
    tasks_by_level: Dict[int, List[str]],
    raw_repo_id: str,
    full_name: str,
    build_ids: List[str],
    commit_shas: List[str],
    ci_provider: str,
) -> Optional[Signature]:
    """
    Build a Celery workflow from task levels.

    Tasks at the same level run in parallel (group).
    Different levels run sequentially (chain).

    Args:
        tasks_by_level: Dict mapping level number to list of task names
        raw_repo_id: Repository ID of raw repo
        full_name: Repository full name (owner/repo)
        build_ids: List of build IDs for log download
        commit_shas: Optional list of commit SHAs for worktree creation
        ci_provider: CI provider string (e.g., "github_actions")

    Returns:
        Celery workflow (chain/group) or None if no tasks
    """
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
                full_name=full_name,
                build_ids=build_ids,
                commit_shas=commit_shas,
                ci_provider=ci_provider,
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
    full_name: str,
    build_ids: List[str],
    commit_shas: List[str],
    ci_provider: str,
    publish_status: bool = False,
) -> Optional[Signature]:
    """
    Create a Celery task signature for a given task name.

    Returns None for unknown tasks or tasks that can't be created
    (e.g., create_worktrees without commit_shas).
    """
    if task_name == "clone_repo":
        return clone_repo.si(
            raw_repo_id=raw_repo_id,
            full_name=full_name,
            publish_status=publish_status,
        )

    elif task_name == "create_worktrees":
        return create_worktrees.si(
            raw_repo_id=raw_repo_id,
            commit_shas=commit_shas,
            publish_status=publish_status,
        )

    elif task_name == "download_build_logs":
        return download_build_logs.si(
            raw_repo_id=raw_repo_id,
            full_name=full_name,
            build_ids=build_ids,
            ci_provider=ci_provider,
            publish_status=publish_status,
        )

    else:
        logger.warning(f"Unknown task name: {task_name}")
        return None
