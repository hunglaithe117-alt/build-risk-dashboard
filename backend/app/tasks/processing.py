"""
Build Processing Tasks using the new DAG-based Feature Pipeline.

This module replaces the old chord/chain pattern with the unified FeaturePipeline.
"""

import logging
from typing import Any, Dict

from bson import ObjectId
import redis
import json

from app.celery_app import celery_app
from app.entities.model_build import ModelBuild
from app.repositories.model_build import ModelBuildRepository
from app.repositories.model_repository import ModelRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.tasks.base import PipelineTask
from app.pipeline.runner import FeaturePipeline
from app.config import settings
from app.pipeline.core.registry import feature_registry
from app.pipeline.constants import TRAVISTORRENT_FEATURES

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
    workflow_run_repo = WorkflowRunRepository(self.db)
    model_build_repo = ModelBuildRepository(self.db)
    model_repo_repo = ModelRepositoryRepository(self.db)

    # Validate workflow run exists
    workflow_run = workflow_run_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not workflow_run:
        logger.error(f"WorkflowRunRaw not found for {repo_id} / {workflow_run_id}")
        return {"status": "error", "message": "WorkflowRunRaw not found"}

    # Validate repository exists
    repo = model_repo_repo.find_by_id(repo_id)
    if not repo:
        logger.error(f"Repository {repo_id} not found")
        return {"status": "error", "message": "Repository not found"}

    model_build = model_build_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not model_build:
        logger.info(f"Creating ModelBuild during processing (not pre-created)")
        build_status = workflow_run.conclusion or "success"
        if build_status == "success":
            build_status = "success"
        elif build_status == "failure":
            build_status = "failure"
        elif build_status == "cancelled":
            build_status = "cancelled"
        elif build_status == "skipped":
            build_status = "skipped"
        elif build_status == "timed_out":
            build_status = "timed_out"
        else:
            logger.warning(f"Unknown build status: {build_status}")
            build_status = "success"

        model_build = ModelBuild(
            repo_id=ObjectId(repo_id),
            workflow_run_id=workflow_run_id,
            status=build_status,
            extraction_status="pending",
        )
        model_build = model_build_repo.insert_one(model_build)

    build_id = str(model_build.id)

    # Notify clients that processing started
    publish_build_update(repo_id, build_id, "in_progress")

    try:
        # Run the unified feature pipeline
        pipeline = FeaturePipeline(
            db=self.db,
            max_workers=4,
        )

        # ALWAYS use TravisTorrent features for Bayesian model training
        # NOTE: repo.requested_feature_names is deprecated and ignored
        feature_names = TRAVISTORRENT_FEATURES

        result = pipeline.run(
            build_sample=model_build,
            repo=repo,
            workflow_run=workflow_run,
            parallel=True,
            features_filter=feature_names,
        )

        updates = {}
        raw_features = result.get("features", {})
        updates["features"] = feature_registry.format_features_for_storage(raw_features)

        if result["status"] == "completed":
            updates["extraction_status"] = "completed"
        elif result["status"] == "partial":
            updates["extraction_status"] = "partial"
        else:
            updates["extraction_status"] = "failed"

        # Handle errors and warnings
        if result.get("errors"):
            updates["error_message"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["error_message"] = "Warning: " + "; ".join(result["warnings"])
            # Check for orphan/fork commits
            if any(
                "Commit not found" in w or "orphan" in w.lower()
                for w in result["warnings"]
            ):
                updates["is_missing_commit"] = True

        # Save to database
        model_build_repo.update_one(build_id, updates)

        # Notify clients of extraction completion
        publish_build_update(repo_id, build_id, updates["extraction_status"])

        logger.info(
            f"Pipeline completed for build {build_id}: "
            f"status={result['status']}, "
            f"features={result.get('feature_count', 0)}"
        )

        return {
            "status": result["status"],
            "build_id": build_id,
            "feature_count": result.get("feature_count", 0),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
        }

    except Exception as e:
        logger.error(f"Pipeline failed for build {build_id}: {e}", exc_info=True)

        # Update model build with error
        model_build_repo.update_one(
            build_id,
            {
                "status": "failed",
                "error_message": str(e),
            },
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
    Reprocess an existing model build with the pipeline.

    Useful for:
    - Retrying failed builds
    - Extracting new features after pipeline updates
    - Testing pipeline changes on existing data
    """
    model_build_repo = ModelBuildRepository(self.db)
    model_build = model_build_repo.find_by_id(ObjectId(build_id))
    if not model_build:
        logger.error(f"ModelBuild {build_id} not found")
        return {"status": "error", "message": "ModelBuild not found"}

    repo_id = str(model_build.repo_id)
    workflow_run_id = model_build.workflow_run_id

    # Delegate to the main processing function
    return process_workflow_run.apply(args=[repo_id, workflow_run_id]).get()


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.reprocess_repo_builds",
    queue="data_processing",
)
def reprocess_repo_builds(self: PipelineTask, repo_id: str) -> Dict[str, Any]:
    """
    Reprocess ALL builds for a repository to re-extract features.

    This is useful when:
    - Feature extractors have been updated/fixed
    - New features have been added
    - Existing builds need their features recalculated

    Unlike import_repo (which fetches new workflow runs from GitHub),
    this task only reprocesses existing builds in the database.
    """
    model_build_repo = ModelBuildRepository(self.db)
    model_repo_repo = ModelRepositoryRepository(self.db)

    # Validate repository exists
    repo = model_repo_repo.find_by_id(repo_id)
    if not repo:
        logger.error(f"Repository {repo_id} not found")
        return {"status": "error", "message": "Repository not found"}

    # Find all builds for this repository
    builds, _ = model_build_repo.list_by_repo(repo_id, limit=0)  # limit=0 means all
    if not builds:
        logger.info(f"No builds found for repository {repo_id}")
        return {
            "status": "completed",
            "builds_queued": 0,
            "message": "No builds to reprocess",
        }

    # Queue each build for reprocessing
    queued_count = 0
    for build in builds:
        try:
            process_workflow_run.delay(repo_id, build.workflow_run_id)
            queued_count += 1
        except Exception as e:
            logger.warning(f"Failed to queue build {build.id} for reprocessing: {e}")

    logger.info(
        f"Queued {queued_count} builds for reprocessing in repository {repo_id}"
    )

    return {
        "status": "queued",
        "builds_queued": queued_count,
        "total_builds": len(builds),
    }
