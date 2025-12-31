"""Shared tasks package for common ingestion and processing logic."""

from app.tasks.shared.ingestion_tasks import (
    aggregate_logs_results,
    clone_repo,
    create_worktree_chunk,
    download_logs_chunk,
)
from app.tasks.shared.processing_helpers import (
    extract_features_for_build,
)
from app.tasks.shared.workflow_builder import (
    build_ingestion_workflow,
)

__all__ = [
    # Ingestion tasks
    "clone_repo",
    "create_worktree_chunk",
    "download_logs_chunk",
    "aggregate_logs_results",
    # Processing helpers
    "extract_features_for_build",
    # Workflow builder
    "build_ingestion_workflow",
]
