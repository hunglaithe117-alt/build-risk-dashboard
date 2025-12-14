"""
Build Processing Tasks using the new DAG-based Feature Pipeline.

This module uses the Hamilton-based pipeline directly for feature extraction.
"""

from app.entities.model_training_build import ModelTrainingBuild
from app.entities.enums import ExtractionStatus, ModelBuildConclusion
import logging
from pathlib import Path
from typing import Any, Dict

from bson import ObjectId
import redis
import json

from app.celery_app import celery_app
from app.entities.model_training_build import ModelTrainingBuild
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.pipeline.hamilton_runner import HamiltonPipeline
from app.pipeline.feature_dag._inputs import (
    build_hamilton_inputs,
    HamiltonInputs,
)
from app.config import settings
from app.paths import REPOS_DIR
from app.pipeline.feature_dag._metadata import (
    format_features_for_storage,
)
from app.repositories.dataset_template_repository import DatasetTemplateRepository

logger = logging.getLogger(__name__)


def publish_build_update(repo_id: str, build_id: str, status: str):
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
    build_run_repo = RawBuildRunRepository(self.db)
    model_build_repo = ModelTrainingBuildRepository(self.db)
    model_repo_repo = ModelRepoConfigRepository(self.db)

    # Validate build run exists
    build_run = build_run_repo.find_by_repo_and_build_id(repo_id, str(workflow_run_id))
    if not build_run:
        logger.error(f"RawBuildRun not found for {repo_id} / {workflow_run_id}")
        return {"status": "error", "message": "RawBuildRun not found"}

    # Validate repository exists
    repo = model_repo_repo.find_by_id(repo_id)
    if not repo:
        logger.error(f"Repository {repo_id} not found")
        return {"status": "error", "message": "Repository not found"}

    model_build = model_build_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not model_build:
        logger.info(f"Creating ModelBuild during processing (not pre-created)")
        conclusion = build_run.conclusion
        status_map = {
            "success": ModelBuildConclusion.SUCCESS,
            "failure": ModelBuildConclusion.FAILURE,
            "cancelled": ModelBuildConclusion.CANCELLED,
            "skipped": ModelBuildConclusion.SKIPPED,
            "timed_out": ModelBuildConclusion.TIMED_OUT,
            "neutral": ModelBuildConclusion.NEUTRAL,
        }
        build_status = status_map.get(
            str(conclusion.value) if conclusion else "", ModelBuildConclusion.UNKNOWN
        )

        model_build = ModelTrainingBuild(
            raw_repo_id=ObjectId(repo_id),
            raw_workflow_run_id=build_run.id,
            model_repo_config_id=ObjectId(repo_id),
            head_sha=build_run.commit_sha,
            build_number=build_run.build_number,
            build_created_at=build_run.created_at,
            build_conclusion=build_status,
            extraction_status=ExtractionStatus.PENDING,
        )
        model_build = model_build_repo.insert_one(model_build)

    build_id = str(model_build.id)

    # Notify clients that processing started
    publish_build_update(repo_id, build_id, "in_progress")

    try:
        # Fetch RawRepository for RepoInput
        raw_repo_repo = RawRepositoryRepository(self.db)
        raw_repo = raw_repo_repo.find_by_id(repo_id)
        if not raw_repo:
            logger.error(f"RawRepository {repo_id} not found")
            return {"status": "error", "message": "RawRepository not found"}

        # Build paths for git operations
        repo_path = REPOS_DIR / repo_id

        # Build all Hamilton inputs using helper function
        inputs = build_hamilton_inputs(
            raw_repo=raw_repo,
            repo_config=repo,
            build_run=build_run,
            repo_path=repo_path,
        )

        # Initialize Hamilton pipeline
        pipeline = HamiltonPipeline(db=self.db)

        # Get feature names from template
        template_repo = DatasetTemplateRepository(self.db)
        template = template_repo.find_by_name("TravisTorrent Full")
        if template:
            feature_names = template.feature_names
        else:
            logger.warning(
                "TravisTorrent Full template not found, using empty feature list"
            )
            feature_names = []

        # Execute Hamilton pipeline
        features = pipeline.run(
            git_history=inputs.git_history,
            git_worktree=inputs.git_worktree,
            repo=inputs.repo,
            workflow_run=inputs.workflow_run,
            repo_config=inputs.repo_config,
            github_client=None,
            features_filter=set(feature_names) if feature_names else None,
        )

        # Build result similar to old wrapper format
        result = {
            "status": "completed",
            "features": features,
            "feature_count": len(features),
            "errors": [],
            "warnings": [],
            "is_missing_commit": not inputs.is_commit_available,
        }

        if not inputs.is_commit_available:
            result["warnings"].append(
                f"Commit {workflow_run.head_sha} not found in repo"
            )

        updates = {}
        raw_features = result.get("features", {})
        updates["features"] = format_features_for_storage(raw_features)

        if result["status"] == "completed":
            updates["extraction_status"] = ExtractionStatus.COMPLETED
        elif result["status"] == "partial":
            updates["extraction_status"] = ExtractionStatus.PARTIAL
        else:
            updates["extraction_status"] = ExtractionStatus.FAILED

        # Handle errors and warnings
        if result.get("errors"):
            updates["error_message"] = "; ".join(result["errors"])
        elif result.get("warnings"):
            updates["error_message"] = "Warning: " + "; ".join(result["warnings"])

        if result.get("is_missing_commit"):
            updates["is_missing_commit"] = True

        model_build_repo.update_one(build_id, updates)

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

        model_build_repo.update_one(
            build_id,
            {
                "extraction_status": ExtractionStatus.FAILED,
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
    model_build_repo = ModelTrainingBuildRepository(self.db)
    model_build = model_build_repo.find_by_id(ObjectId(build_id))
    if not model_build:
        logger.error(f"ModelTrainingBuild {build_id} not found")
        return {"status": "error", "message": "ModelTrainingBuild not found"}

    repo_id = str(model_build.repo_id)
    workflow_run_id = model_build.workflow_run_id

    process_workflow_run.delay(repo_id, workflow_run_id)

    return {
        "status": "queued",
        "build_id": build_id,
        "message": f"Build {build_id} queued for reprocessing",
    }


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
    model_build_repo = ModelTrainingBuildRepository(self.db)
    model_repo_repo = ModelRepoConfigRepository(self.db)

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
