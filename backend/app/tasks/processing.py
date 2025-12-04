"""
Build Processing Tasks using the new DAG-based Feature Pipeline.

This module replaces the old chord/chain pattern with the unified FeaturePipeline.
"""
import logging
from typing import Any, Dict

from bson import ObjectId

from app.celery_app import celery_app
from app.models.entities.build_sample import BuildSample
from app.repositories.build_sample import BuildSampleRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.tasks.base import PipelineTask
from app.pipeline.runner import FeaturePipeline, run_feature_pipeline
from app.config import settings
import redis
import json

logger = logging.getLogger(__name__)


def publish_build_update(repo_id: str, build_id: str, status: str):
    """Publish build status update via Redis pub/sub."""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.publish(
            "events",
            json.dumps(
                {
                    "type": "BUILD_UPDATE",
                    "payload": {
                        "repo_id": repo_id,
                        "build_id": build_id,
                        "status": status,
                    },
                }
            ),
        )
    except Exception as e:
        logger.error(f"Failed to publish build update: {e}")


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.process_workflow_run",
    queue="data_processing",
)
def process_workflow_run(
    self: PipelineTask, repo_id: str, workflow_run_id: int
) -> Dict[str, Any]:
    """
    Process a workflow run using the new DAG-based feature pipeline.
    
    This replaces the old chord/chain pattern with a unified pipeline execution.
    The pipeline handles:
    - Resource initialization (git repo, github client, log storage)
    - DAG-based feature extraction with proper dependency resolution
    - Parallel execution of independent features
    - Error handling and warnings
    """
    workflow_run_repo = WorkflowRunRepository(self.db)
    build_sample_repo = BuildSampleRepository(self.db)
    repo_repo = ImportedRepositoryRepository(self.db)

    # Validate workflow run exists
    workflow_run = workflow_run_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not workflow_run:
        logger.error(f"WorkflowRunRaw not found for {repo_id} / {workflow_run_id}")
        return {"status": "error", "message": "WorkflowRunRaw not found"}

    # Validate repository exists
    repo = repo_repo.find_by_id(repo_id)
    if not repo:
        logger.error(f"Repository {repo_id} not found")
        return {"status": "error", "message": "Repository not found"}

    # Find or create BuildSample
    build_sample = build_sample_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not build_sample:
        build_sample = BuildSample(
            repo_id=ObjectId(repo_id),
            workflow_run_id=workflow_run_id,
            status="pending",
            tr_build_number=workflow_run.run_number,
            tr_original_commit=workflow_run.head_sha,
        )
        build_sample = build_sample_repo.insert_one(build_sample)

    build_id = str(build_sample.id)
    
    # Notify clients that processing started
    publish_build_update(repo_id, build_id, "in_progress")

    try:
        # Run the unified feature pipeline
        pipeline = FeaturePipeline(
            db=self.db,
            max_workers=4,
            use_definitions=True,
            filter_active_only=True,
        )
        
        result = pipeline.run(
            build_sample=build_sample,
            repo=repo,
            workflow_run=workflow_run,
            parallel=True,
        )
        
        # Prepare updates for BuildSample
        updates = result.get("features", {}).copy()
        
        # Set status
        if result["status"] == "completed":
            updates["status"] = "completed"
        elif result["status"] == "partial":
            updates["status"] = "completed"  # Still mark as completed but with warnings
        else:
            updates["status"] = "failed"
        
        # Handle errors and warnings
        if result.get("errors"):
            updates["error_message"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["error_message"] = "Warning: " + "; ".join(result["warnings"])
            # Check for orphan/fork commits
            if any("Commit not found" in w or "orphan" in w.lower() for w in result["warnings"]):
                updates["is_missing_commit"] = True
        
        # Save to database
        build_sample_repo.update_one(build_id, updates)
        
        # Notify clients of completion
        publish_build_update(repo_id, build_id, updates["status"])
        
        logger.info(
            f"Pipeline completed for build {build_id}: "
            f"status={result['status']}, "
            f"features={result.get('feature_count', 0)}, "
            f"ml_features={result.get('ml_feature_count', 0)}"
        )
        
        return {
            "status": result["status"],
            "build_id": build_id,
            "feature_count": result.get("feature_count", 0),
            "ml_feature_count": result.get("ml_feature_count", 0),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
        }
        
    except Exception as e:
        logger.error(f"Pipeline failed for build {build_id}: {e}", exc_info=True)
        
        # Update build sample with error
        build_sample_repo.update_one(
            build_id,
            {
                "status": "failed",
                "error_message": str(e),
            }
        )
        
        publish_build_update(repo_id, build_id, "failed")
        
        return {
            "status": "failed",
            "build_id": build_id,
            "error": str(e),
        }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.reprocess_build",
    queue="data_processing",
)
def reprocess_build(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Reprocess an existing build sample with the new pipeline.
    
    Useful for:
    - Retrying failed builds
    - Extracting new features after pipeline updates
    - Testing pipeline changes on existing data
    """
    build_sample_repo = BuildSampleRepository(self.db)
    repo_repo = ImportedRepositoryRepository(self.db)
    workflow_run_repo = WorkflowRunRepository(self.db)
    
    build_sample = build_sample_repo.find_by_id(ObjectId(build_id))
    if not build_sample:
        logger.error(f"BuildSample {build_id} not found")
        return {"status": "error", "message": "BuildSample not found"}
    
    repo_id = str(build_sample.repo_id)
    workflow_run_id = build_sample.workflow_run_id
    
    # Delegate to the main processing function
    return process_workflow_run.apply(args=[repo_id, workflow_run_id]).get()


# =============================================================================
# Legacy Compatibility - These are kept for backwards compatibility but now
# delegate to the unified pipeline. They can be removed once all callers
# are updated.
# =============================================================================

@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_build_log_features",
    queue="data_processing",
)
def extract_build_log_features(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Legacy task - now uses unified pipeline.
    Kept for backwards compatibility.
    """
    logger.warning(
        f"extract_build_log_features is deprecated. "
        f"Use process_workflow_run instead for build {build_id}"
    )
    result = run_feature_pipeline(self.db, build_id)
    return result.get("features", {})


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_git_features",
    queue="data_processing",
)
def extract_git_features(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Legacy task - now uses unified pipeline.
    Kept for backwards compatibility.
    """
    logger.warning(
        f"extract_git_features is deprecated. "
        f"Use process_workflow_run instead for build {build_id}"
    )
    result = run_feature_pipeline(self.db, build_id)
    return result.get("features", {})


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_repo_snapshot_features",
    queue="data_processing",
)
def extract_repo_snapshot_features(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Legacy task - now uses unified pipeline.
    Kept for backwards compatibility.
    """
    logger.warning(
        f"extract_repo_snapshot_features is deprecated. "
        f"Use process_workflow_run instead for build {build_id}"
    )
    result = run_feature_pipeline(self.db, build_id)
    return result.get("features", {})


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_github_discussion_features",
    queue="data_processing",
)
def extract_github_discussion_features(
    self: PipelineTask, build_id: str
) -> Dict[str, Any]:
    """
    Legacy task - now uses unified pipeline.
    Kept for backwards compatibility.
    """
    logger.warning(
        f"extract_github_discussion_features is deprecated. "
        f"Use process_workflow_run instead for build {build_id}"
    )
    result = run_feature_pipeline(self.db, build_id)
    return result.get("features", {})


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.finalize_build_sample",
    queue="data_processing",
)
def finalize_build_sample(
    self: PipelineTask, results: list, build_id: str
) -> Dict[str, Any]:
    """
    Legacy task - no longer needed with unified pipeline.
    Kept for backwards compatibility but does nothing.
    """
    logger.warning(
        f"finalize_build_sample is deprecated and no longer needed. "
        f"The unified pipeline handles finalization for build {build_id}"
    )
    return {"status": "noop", "build_id": build_id}
