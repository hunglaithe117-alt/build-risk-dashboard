"""
Shared Processing Helpers - Common feature extraction logic.

These helpers are used by both model_processing.py and enrichment_processing.py
to extract features using the Hamilton pipeline.
"""

from app.entities.repo_config_base import RepoConfigBase
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.entities.raw_build_run import RawBuildRun
from app.entities.raw_repository import RawRepository
from app.entities.pipeline_run import (
    PipelineRun,
    PipelineRunStatus,
    PipelineCategory,
    NodeExecutionResult,
    NodeExecutionStatus,
)
from app.repositories.pipeline_run import PipelineRunRepository
from app.tasks.pipeline.hamilton_runner import HamiltonPipeline
from app.tasks.pipeline.feature_dag._inputs import build_hamilton_inputs, BuildLogsInput
from app.tasks.pipeline.feature_dag._metadata import format_features_for_storage
from app.paths import REPOS_DIR, LOGS_DIR

logger = logging.getLogger(__name__)


def _save_pipeline_run(
    db,
    raw_repo: RawRepository,
    raw_build_run: RawBuildRun,
    pipeline: HamiltonPipeline,
    status: str,
    features: List[str],
    errors: List[str],
    category: PipelineCategory,
    output_build_id: Optional[str] = None,
) -> None:
    """
    Save pipeline execution results to database.

    Args:
        db: Database session
        raw_repo: RawRepository entity
        raw_build_run: RawBuildRun entity
        pipeline: HamiltonPipeline instance (with execution results)
        status: Execution status ("completed" or "failed")
        features: List of extracted feature names
        errors: List of error messages
        category: Pipeline category (model_training or dataset_enrichment)
        output_build_id: ID of the output entity (ModelTrainingBuild or DatasetEnrichmentBuild)
    """
    try:
        execution_result = pipeline.get_execution_results()

        # Create PipelineRun entity
        pipeline_run = PipelineRun(
            category=category,
            raw_repo_id=raw_repo.id,
            raw_build_run_id=raw_build_run.id,
            status=(
                PipelineRunStatus.COMPLETED
                if status == "completed"
                else PipelineRunStatus.FAILED
            ),
            feature_count=len(features),
            features_extracted=features,
            errors=errors,
        )

        # Set output entity reference based on category
        if output_build_id:
            from bson import ObjectId

            if category == PipelineCategory.MODEL_TRAINING:
                pipeline_run.training_build_id = ObjectId(output_build_id)
            else:
                pipeline_run.enrichment_build_id = ObjectId(output_build_id)

        if execution_result:
            pipeline_run.started_at = execution_result.started_at
            pipeline_run.completed_at = execution_result.completed_at
            pipeline_run.duration_ms = execution_result.duration_ms
            pipeline_run.nodes_executed = execution_result.nodes_executed
            pipeline_run.nodes_succeeded = execution_result.nodes_succeeded
            pipeline_run.nodes_failed = execution_result.nodes_failed
            pipeline_run.nodes_skipped = execution_result.nodes_skipped
            pipeline_run.errors.extend(execution_result.errors)

            # Add node-level results
            for node_info in execution_result.node_results:
                node_result = NodeExecutionResult(
                    node_name=node_info.node_name,
                    status=(
                        NodeExecutionStatus.SUCCESS
                        if node_info.success
                        else NodeExecutionStatus.FAILED
                    ),
                    started_at=node_info.started_at,
                    completed_at=node_info.completed_at,
                    duration_ms=node_info.duration_ms,
                    error=node_info.error,
                )
                pipeline_run.add_node_result(node_result)
        else:
            # If no tracking, just set timestamps
            now = datetime.now(timezone.utc)
            pipeline_run.started_at = now
            pipeline_run.completed_at = now

        # Save to database
        pipeline_run_repo = PipelineRunRepository(db)
        pipeline_run_repo.insert_one(pipeline_run)

        logger.debug(
            f"Saved pipeline run ({category.value}) for build {raw_build_run.build_id}: "
            f"{pipeline_run.nodes_succeeded}/{pipeline_run.nodes_executed} nodes succeeded"
        )

    except Exception as e:
        logger.warning(f"Failed to save pipeline run: {e}")


def extract_features_for_build(
    db,
    raw_repo: RawRepository,
    repo_config: RepoConfigBase,  # Can be ModelRepoConfig or DatasetRepoConfig
    raw_build_run: RawBuildRun,
    selected_features: List[str] = [],
    github_client=None,
    save_run: bool = True,
    category: PipelineCategory = PipelineCategory.MODEL_TRAINING,
    output_build_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract features for a single build using HamiltonPipeline.

    Always returns a result dict containing:
    - status: "completed", "partial", or "failed"
    - features: Extracted features dict (formatted for storage)
    - feature_count: Number of features extracted
    - errors: List of error messages
    - warnings: List of warning messages
    - is_missing_commit: Whether the commit was missing from repo

    Args:
        db: Database session
        raw_repo: RawRepository entity
        repo_config: ModelRepoConfig or DatasetRepoConfig entity
        raw_build_run: RawBuildRun entity
        selected_features: Optional list of features to extract
        github_client: Optional GitHub client for API calls
        save_run: Whether to save pipeline run to database (default: True)
        category: Pipeline category for tracking (default: MODEL_TRAINING)
        output_build_id: ID of the output entity (ModelTrainingBuild or DatasetEnrichmentBuild)

    Returns:
        Dictionary with status, features, errors, warnings, etc.
    """
    repo_path = REPOS_DIR / str(raw_repo.id)
    pipeline = None

    try:
        # Build all Hamilton inputs using helper function
        # Pass worktrees_base so GIT_WORKTREE resource is available
        from app.paths import WORKTREES_DIR

        worktrees_base = WORKTREES_DIR / str(raw_repo.id)

        inputs = build_hamilton_inputs(
            raw_repo=raw_repo,
            repo_config=repo_config,
            build_run=raw_build_run,
            repo_path=repo_path,
            worktrees_base=worktrees_base,
        )

        # Execute Hamilton pipeline with tracking enabled
        pipeline = HamiltonPipeline(db=db, enable_tracking=True)

        # Build logs input - LOGS_DIR/{raw_repo_id}/{raw_build_run_id}/*.log
        logs_dir = LOGS_DIR / str(raw_repo.id) / str(raw_build_run.id)
        build_logs_input = BuildLogsInput.from_path(logs_dir)

        features = pipeline.run(
            git_history=inputs.git_history,
            git_worktree=inputs.git_worktree,
            repo=inputs.repo,
            build_run=inputs.build_run,
            repo_config=inputs.repo_config,
            github_client=github_client,
            build_logs=build_logs_input,
            features_filter=set(selected_features) if selected_features else None,
        )

        formatted_features = format_features_for_storage(features)

        # Get skipped features and missing resources from pipeline
        skipped_features = list(pipeline.skipped_features) if pipeline else []
        missing_resources = list(pipeline.missing_resources) if pipeline else []

        result = {
            "status": "completed",
            "features": formatted_features,
            "feature_count": len(formatted_features),
            "errors": [],
            "warnings": [],
            "is_missing_commit": not inputs.is_commit_available,
            "skipped_features": skipped_features,
            "missing_resources": missing_resources,
        }

        # Adjust status if features were skipped
        if skipped_features:
            result["status"] = "partial"
            result["warnings"].append(
                f"Skipped {len(skipped_features)} features due to missing resources"
            )

        if not inputs.is_commit_available:
            result["warnings"].append(
                f"Commit {raw_build_run.commit_sha} not found in repo"
            )

        # Save pipeline run to database
        if save_run and pipeline:
            _save_pipeline_run(
                db=db,
                raw_repo=raw_repo,
                raw_build_run=raw_build_run,
                pipeline=pipeline,
                status="completed",
                features=list(formatted_features.keys()),
                errors=[],
                category=category,
                output_build_id=output_build_id,
            )

        return result

    except Exception as e:
        logger.error(
            f"Pipeline failed for build {raw_build_run.build_id}: {e}",
            exc_info=True,
        )

        # Save failed pipeline run
        if save_run and pipeline:
            _save_pipeline_run(
                db=db,
                raw_repo=raw_repo,
                raw_build_run=raw_build_run,
                pipeline=pipeline,
                status="failed",
                features=[],
                errors=[str(e)],
                category=category,
                output_build_id=output_build_id,
            )

        return {
            "status": "failed",
            "features": {},
            "feature_count": 0,
            "errors": [str(e)],
            "warnings": [],
            "is_missing_commit": False,
        }
