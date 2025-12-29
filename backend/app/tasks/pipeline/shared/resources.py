"""
Resource and Input Registry for Hamilton Pipeline.

This module provides:
- FeatureResource enum: Resources that features can depend on
- InputSpec: Specification for each Hamilton DAG input
- INPUT_REGISTRY: Single source of truth for all inputs
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FeatureResource(str, Enum):
    """
    Resources required by features.

    Resources form a DAG with dependencies.
    """

    # Core inputs (always available from DB, no ingestion needed)
    BUILD_RUN = "build_run"  # Single RawBuildRun entity (current build)
    REPO = "repo"  # RawRepository metadata
    FEATURE_CONFIG = "feature_config"  # Feature/repo configuration

    # Collection access
    RAW_BUILD_RUNS = "raw_build_runs"  # raw_build_runs collection
    MODEL_TRAINING_BUILDS = "model_training_builds"  # model_training_builds collection

    # Git resources (require ingestion)
    GIT_HISTORY = "git_history"  # Git bare repo (clone_repo task)
    GIT_WORKTREE = "git_worktree"  # Git worktree (create_worktrees task)

    # External resources
    GITHUB_API = "github_api"  # GitHub API client (on-demand, no ingestion)
    BUILD_LOGS = "build_logs"  # CI job logs (download_build_logs task)


@dataclass
class InputSpec:
    """
    Specification for a Hamilton DAG input.

    Consolidates all metadata about an input in one place:
    - How it maps to a FeatureResource
    - Whether it's always available (core) or requires preparation
    - How to check if it's available at runtime

    Usage:
        To add a new input:
        1. Add enum value to FeatureResource (if new resource type)
        2. Add InputSpec to INPUT_REGISTRY below
        That's it! No need to edit multiple files.
    """

    name: str  # Hamilton input key (e.g., "git_history")
    resource: FeatureResource  # Corresponding resource enum
    is_core: bool = False  # Always available from DB (no ingestion needed)
    availability_attr: Optional[str] = None  # Attribute to check (e.g., "is_ready")
    ingestion_tasks: List[str] = field(default_factory=list)  # Tasks to prepare this input


# =============================================================================
# INPUT REGISTRY - Single Source of Truth
# =============================================================================
# To add a new input source:
# 1. Add to FeatureResource enum above (if new resource type)
# 2. Create Input dataclass in feature_dag/_inputs.py
# 3. Add InputSpec entry below
# That's all! hamilton_runner.py will automatically handle it.

INPUT_REGISTRY: Dict[str, InputSpec] = {
    # Core inputs - always available from DB
    "repo": InputSpec(
        name="repo",
        resource=FeatureResource.REPO,
        is_core=True,
    ),
    "build_run": InputSpec(
        name="build_run",
        resource=FeatureResource.BUILD_RUN,
        is_core=True,
    ),
    "feature_config": InputSpec(
        name="feature_config",
        resource=FeatureResource.FEATURE_CONFIG,
        is_core=True,
    ),
    "raw_build_runs": InputSpec(
        name="raw_build_runs",
        resource=FeatureResource.RAW_BUILD_RUNS,
        is_core=True,
    ),
    "model_training_builds": InputSpec(
        name="model_training_builds",
        resource=FeatureResource.MODEL_TRAINING_BUILDS,
        is_core=True,
    ),
    # Git resources - require ingestion
    "git_history": InputSpec(
        name="git_history",
        resource=FeatureResource.GIT_HISTORY,
        is_core=False,
        availability_attr="is_commit_available",
        ingestion_tasks=["clone_repo"],
    ),
    "git_worktree": InputSpec(
        name="git_worktree",
        resource=FeatureResource.GIT_WORKTREE,
        is_core=False,
        availability_attr="is_ready",
        ingestion_tasks=["clone_repo", "create_worktrees"],
    ),
    # External resources - on-demand
    "github_client": InputSpec(
        name="github_client",
        resource=FeatureResource.GITHUB_API,
        is_core=False,
        availability_attr=None,
    ),
    "build_logs": InputSpec(
        name="build_logs",
        resource=FeatureResource.BUILD_LOGS,
        is_core=False,
        availability_attr="is_available",
        ingestion_tasks=["download_build_logs"],
    ),
}


def get_input_resource_names() -> frozenset:
    """Get all input resource names (replaces INPUT_RESOURCE_NAMES constant)."""
    return frozenset(INPUT_REGISTRY.keys())


def check_resource_availability(inputs: Dict[str, Any]) -> set:
    """
    Check which resources are available based on provided inputs.

    Args:
        inputs: Dictionary of input name -> input object

    Returns:
        Set of available resource values (strings)
    """
    available = set()

    for name, spec in INPUT_REGISTRY.items():
        if spec.is_core:
            # Core resources are always available
            available.add(spec.resource.value)
        elif name in inputs:
            input_obj = inputs[name]
            if input_obj is None:
                continue

            if spec.availability_attr:
                # Check specific attribute
                if getattr(input_obj, spec.availability_attr, False):
                    available.add(spec.resource.value)
            else:
                # No attr check needed, presence is enough
                available.add(spec.resource.value)

    return available


# Task dependency graph
# Used to determine parallel execution order in Celery workflows
TASK_DEPENDENCIES: Dict[str, List[str]] = {
    "clone_repo": [],
    "create_worktrees": ["clone_repo"],
    "download_build_logs": [],
}

# Resource → Leaf tasks only (now derived from INPUT_REGISTRY for consistency)
RESOURCE_LEAF_TASKS: Dict[FeatureResource, List[str]] = {
    spec.resource: spec.ingestion_tasks for spec in INPUT_REGISTRY.values()
}

# Celery task paths
# Maps logical task names to their fully qualified Celery task names
INGESTION_TASK_TO_CELERY: Dict[str, str] = {
    "clone_repo": "app.tasks.shared.clone_repo",
    "download_build_logs": "app.tasks.shared.download_build_logs",
    "create_worktrees": "app.tasks.shared.create_worktrees",
}
