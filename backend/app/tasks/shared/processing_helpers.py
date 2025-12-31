"""
Shared Processing Helpers - Common feature extraction logic.

These helpers are used by both model_processing.py and enrichment_processing.py
to extract features using the Hamilton pipeline.

Features are stored in FeatureVector (single source of truth).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.entities.enums import ExtractionStatus
from app.entities.feature_audit_log import (
    AuditLogCategory,
    FeatureAuditLog,
    NodeExecutionResult,
    NodeExecutionStatus,
)
from app.entities.raw_build_run import RawBuildRun
from app.entities.raw_repository import RawRepository
from app.repositories.feature_audit_log import FeatureAuditLogRepository
from app.repositories.feature_vector import FeatureVectorRepository
from app.tasks.pipeline.feature_dag._metadata import format_features_for_storage
from app.tasks.pipeline.hamilton_runner import HamiltonPipeline

logger = logging.getLogger(__name__)


def _save_audit_log(
    db,
    raw_repo: RawRepository,
    raw_build_run: RawBuildRun,
    pipeline: HamiltonPipeline,
    features: List[str],
    errors: List[str],
    category: AuditLogCategory,
    output_build_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    version_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> None:
    """
    Save pipeline execution results to database.

    Args:
        db: Database session
        raw_repo: RawRepository entity
        raw_build_run: RawBuildRun entity
        pipeline: HamiltonPipeline instance (with execution results)
        features: List of extracted feature names
        errors: List of error messages
        category: Pipeline category (model_training or dataset_enrichment)
        output_build_id: ID of the output entity (ModelTrainingBuild or DatasetEnrichmentBuild)
        correlation_id: Correlation ID for tracing
        version_id: DatasetVersion ID (for dataset_enrichment category)
        dataset_id: Dataset ID (for dataset_enrichment category)
    """
    try:
        # Get correlation_id from context if not provided
        if not correlation_id:
            from app.core.tracing import TracingContext

            correlation_id = TracingContext.get_correlation_id()

        execution_result = pipeline.get_execution_results()

        # Create FeatureAuditLog entity
        audit_log = FeatureAuditLog(
            correlation_id=correlation_id if correlation_id else None,
            category=category,
            raw_repo_id=raw_repo.id,
            raw_build_run_id=raw_build_run.id,
            feature_count=len(features),
            features_extracted=features,
            errors=errors,
        )

        # Set output entity reference based on category
        if output_build_id:
            if category == AuditLogCategory.MODEL_TRAINING:
                audit_log.training_build_id = ObjectId(output_build_id)
            else:
                audit_log.enrichment_build_id = ObjectId(output_build_id)

        # Set version_id and dataset_id for enrichment category
        if version_id:
            audit_log.version_id = ObjectId(version_id)
        if dataset_id:
            audit_log.dataset_id = ObjectId(dataset_id)

        if execution_result:
            audit_log.started_at = execution_result.started_at
            audit_log.completed_at = execution_result.completed_at
            audit_log.duration_ms = execution_result.duration_ms
            audit_log.nodes_executed = execution_result.nodes_executed
            audit_log.nodes_succeeded = execution_result.nodes_succeeded
            audit_log.nodes_failed = execution_result.nodes_failed
            audit_log.nodes_skipped = execution_result.nodes_skipped
            audit_log.errors.extend(execution_result.errors)

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
                    resources_used=node_info.resources_used,
                )

                # Populate feature values if this node corresponds to a requested feature
                if node_info.success and node_info.node_name in features:
                    node_result.features_extracted = [node_info.node_name]
                    if hasattr(node_info, "result") and node_info.result is not None:
                        node_result.feature_values = {node_info.node_name: node_info.result}

                audit_log.add_node_result(node_result)
        else:
            # If no tracking, just set timestamps
            now = datetime.now(timezone.utc)
            audit_log.started_at = now
            audit_log.completed_at = now

        # Save to database
        audit_log_repo = FeatureAuditLogRepository(db)
        audit_log_repo.insert_one(audit_log)

        logger.debug(
            f"Saved audit log ({category.value}) for build {raw_build_run.ci_run_id}: "
            f"{audit_log.nodes_succeeded}/{audit_log.nodes_executed} nodes succeeded"
        )

    except Exception as e:
        logger.warning(f"Failed to save audit log: {e}")


def extract_features_for_build(
    db,
    raw_repo: RawRepository,
    feature_config: Dict[str, Any],
    raw_build_run: RawBuildRun,
    selected_features: List[str],
    save_run: bool = True,
    category: AuditLogCategory = AuditLogCategory.MODEL_TRAINING,
    output_build_id: Optional[str] = None,
    version_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract features for a single build using HamiltonPipeline.

    Features are saved to FeatureVector (single source of truth).

    Always returns a result dict containing:
    - status: "completed", "partial", or "failed"
    - features: Extracted features dict (formatted for storage)
    - feature_count: Number of features extracted
    - feature_vector_id: ObjectId of the FeatureVector document
    - errors: List of error messages
    - warnings: List of warning messages
    - is_missing_commit: Whether the commit was missing from repo

    Args:
        db: Database session
        raw_repo: RawRepository entity
        feature_config: Feature configuration dict
        raw_build_run: RawBuildRun entity
        selected_features: List of features to extract
        github_client: Optional GitHub client for API calls
        save_run: Whether to save pipeline run to database (default: True)
        category: Pipeline category for tracking (default: MODEL_TRAINING)
        output_build_id: ID of the output entity
        version_id: DatasetVersion ID (for DATASET_ENRICHMENT category)
        dataset_id: Dataset ID (for DATASET_ENRICHMENT category)

    Returns:
        Dictionary with status, features, feature_vector_id, errors, warnings, etc.
    """
    from app.tasks.pipeline.input_preparer import prepare_pipeline_input

    pipeline = None
    feature_vector_repo = FeatureVectorRepository(db)

    try:
        from app.services.github.github_client import get_public_github_client
        from app.tasks.pipeline.feature_dag._inputs import GitHubClientInput

        client = get_public_github_client()
        github_client_input = GitHubClientInput(client=client, full_name=raw_repo.full_name)

        # Prepare all inputs and filter features by available resources
        prepared = prepare_pipeline_input(
            raw_repo=raw_repo,
            feature_config=feature_config,
            raw_build_run=raw_build_run,
            selected_features=selected_features if selected_features else None,
            github_client=github_client_input,
        )

        # Execute Hamilton pipeline
        pipeline = HamiltonPipeline(db=db, enable_tracking=True)
        features = pipeline.execute(prepared)

        formatted_features = format_features_for_storage(features)

        # Get skipped features and missing resources from pipeline
        skipped_features = list(pipeline.skipped_features) if pipeline else []
        missing_resources = list(pipeline.missing_resources) if pipeline else []

        # Validate required model features are present
        try:
            from app.services.risk_model.inference import STATIC_FEATURES, TEMPORAL_FEATURES

            required_features = set(TEMPORAL_FEATURES + STATIC_FEATURES)
            extracted_features = set(formatted_features.keys())
            missing_model_features = required_features - extracted_features

            if missing_model_features:
                logger.warning(
                    f"Build {raw_build_run.ci_run_id} missing {len(missing_model_features)} "
                    f"model features: {sorted(missing_model_features)}"
                )
        except ImportError:
            # Model not available, skip validation
            missing_model_features = set()

        # Determine extraction status
        if skipped_features:
            extraction_status = ExtractionStatus.PARTIAL
        else:
            extraction_status = ExtractionStatus.COMPLETED

        # Get tr_prev_build for temporal chain indexing
        tr_prev_build = formatted_features.get("tr_prev_build")

        # Save to FeatureVector (single source of truth)
        feature_vector = feature_vector_repo.upsert_features(
            raw_repo_id=raw_repo.id,
            raw_build_run_id=raw_build_run.id,
            features=formatted_features,
            extraction_status=extraction_status,
            dag_version="1.0",
            tr_prev_build=tr_prev_build,
            is_missing_commit=not prepared.is_commit_available,
            missing_resources=missing_resources,
            skipped_features=skipped_features,
        )

        result = {
            "status": extraction_status.value,
            "features": formatted_features,
            "feature_count": len(formatted_features),
            "feature_vector_id": feature_vector.id,
            "errors": [],
            "warnings": [],
            "is_missing_commit": not prepared.is_commit_available,
            "skipped_features": skipped_features,
            "missing_resources": missing_resources,
        }

        # Adjust status if features were skipped
        if skipped_features:
            result["warnings"].append(
                f"Skipped {len(skipped_features)} features: {skipped_features}. "
                f"Missing resources: {missing_resources}"
            )

        if missing_model_features:
            result["warnings"].append(
                f"Missing {len(missing_model_features)} model features: "
                f"{sorted(missing_model_features)}"
            )

        if not prepared.is_commit_available:
            result["warnings"].append(f"Commit {raw_build_run.commit_sha} not found in repo")

        # Save audit log to database
        if save_run and pipeline:
            _save_audit_log(
                db=db,
                raw_repo=raw_repo,
                raw_build_run=raw_build_run,
                pipeline=pipeline,
                features=list(formatted_features.keys()),
                errors=[],
                category=category,
                output_build_id=output_build_id,
                version_id=version_id,
                dataset_id=dataset_id,
            )

        return result

    except Exception as e:
        logger.error(
            f"Pipeline failed for build {raw_build_run.ci_run_id}: {e}",
            exc_info=True,
        )

        # Save failed FeatureVector
        try:
            feature_vector = feature_vector_repo.upsert_features(
                raw_repo_id=raw_repo.id,
                raw_build_run_id=raw_build_run.id,
                features={},
                extraction_status=ExtractionStatus.FAILED,
                extraction_error=str(e),
                dag_version="1.0",
            )
            feature_vector_id = feature_vector.id
        except Exception as save_error:
            logger.warning(f"Failed to save failed FeatureVector: {save_error}")
            feature_vector_id = None

        # Save failed audit log
        if save_run and pipeline:
            _save_audit_log(
                db=db,
                raw_repo=raw_repo,
                raw_build_run=raw_build_run,
                pipeline=pipeline,
                features=[],
                errors=[str(e)],
                category=category,
                output_build_id=output_build_id,
                version_id=version_id,
                dataset_id=dataset_id,
            )

        return {
            "status": "failed",
            "features": {},
            "feature_count": 0,
            "feature_vector_id": feature_vector_id,
            "errors": [str(e)],
            "warnings": [],
            "is_missing_commit": False,
        }
