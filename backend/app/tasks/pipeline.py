"""
Pipeline Celery Tasks - New tasks using the DAG-based pipeline.

These tasks can replace the chord/chain pattern in processing.py
for simpler, more maintainable code.
"""

import logging
from typing import Any, Dict

from bson import ObjectId

from app.celery_app import celery_app
from app.tasks.base import PipelineTask
from app.pipeline.runner import FeaturePipeline, run_feature_pipeline
from app.repositories.build_sample import BuildSampleRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.models.entities.build_sample import BuildSample

import redis
import json
from app.config import settings

logger = logging.getLogger(__name__)


def publish_build_update(repo_id: str, build_id: str, status: str):
    """Publish build status update via Redis."""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.publish(
            "events",
            json.dumps({
                "type": "BUILD_UPDATE",
                "payload": {
                    "repo_id": repo_id,
                    "build_id": build_id,
                    "status": status,
                },
            }),
        )
    except Exception as e:
        logger.error(f"Failed to publish build update: {e}")


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.pipeline.process_build_pipeline",
    queue="data_processing",
)
def process_build_pipeline(
    self: PipelineTask, repo_id: str, workflow_run_id: int
) -> Dict[str, Any]:
    """
    Process a workflow run using the new DAG-based pipeline.
    
    This is a single task that replaces the chord/chain pattern.
    The pipeline handles all dependencies internally.
    """
    workflow_run_repo = WorkflowRunRepository(self.db)
    build_sample_repo = BuildSampleRepository(self.db)
    repo_repo = ImportedRepositoryRepository(self.db)

    # Fetch workflow run
    workflow_run = workflow_run_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not workflow_run:
        logger.error(f"WorkflowRun not found for {repo_id} / {workflow_run_id}")
        return {"status": "error", "message": "WorkflowRun not found"}

    # Fetch repository
    repo = repo_repo.find_by_id(repo_id)
    if not repo:
        logger.error(f"Repository {repo_id} not found")
        return {"status": "error", "message": "Repository not found"}

    # Get or create build sample
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
    
    # Publish processing started
    publish_build_update(repo_id, build_id, "in_progress")

    # Run the feature pipeline
    pipeline = FeaturePipeline(self.db)
    result = pipeline.run(build_sample, repo, workflow_run)

    # Save results
    if result["features"]:
        updates = result["features"].copy()
        updates["status"] = result["status"]
        
        if result["errors"]:
            updates["error_message"] = "; ".join(result["errors"])
        elif result["warnings"]:
            updates["error_message"] = "Warning: " + "; ".join(result["warnings"])
            # Check for missing commit warning
            if any("Commit not found" in w for w in result["warnings"]):
                updates["is_missing_commit"] = True
        
        build_sample_repo.update_one(build_id, updates)

    # Publish completion
    publish_build_update(repo_id, build_id, result["status"])

    logger.info(
        f"Pipeline completed for {repo_id}/{workflow_run_id}: "
        f"status={result['status']}, features={len(result['features'])}"
    )

    return {
        "status": result["status"],
        "build_id": build_id,
        "features_extracted": len(result["features"]),
        "errors": result["errors"],
        "warnings": result["warnings"],
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.pipeline.reprocess_build",
    queue="data_processing",
)
def reprocess_build(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    """
    Reprocess an existing build sample.
    
    Useful for:
    - Re-extracting features after code changes
    - Recovering from partial failures
    - Updating with new feature nodes
    """
    result = run_feature_pipeline(self.db, build_id)
    
    if result["status"] == "completed":
        logger.info(f"Reprocessed build {build_id} successfully")
    else:
        logger.warning(f"Reprocessed build {build_id} with status: {result['status']}")
    
    return result
