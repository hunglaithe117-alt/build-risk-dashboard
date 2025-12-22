"""Shared tasks package for common ingestion and processing logic."""

from app.tasks.shared.ingestion_tasks import (
    aggregate_logs_results,
    clone_repo,
    create_worktree_chunk,
    download_logs_chunk,
    finalize_worktrees,
)
from app.tasks.shared.ingestion_tracker import (
    IngestionContext,
    IngestionProgress,
    IngestionStage,
    IngestionTracker,
    create_tracker_for_enrichment,
    create_tracker_for_model,
    create_tracker_for_repo,
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
    "finalize_worktrees",
    "download_logs_chunk",
    "aggregate_logs_results",
    # Processing helpers
    "extract_features_for_build",
    # Workflow builder
    "build_ingestion_workflow",
    # Ingestion tracker
    "IngestionTracker",
    "IngestionStage",
    "IngestionProgress",
    "IngestionContext",
    "create_tracker_for_model",
    "create_tracker_for_enrichment",
    "create_tracker_for_repo",
]
