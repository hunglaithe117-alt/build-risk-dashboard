import logging
from typing import Any, Dict, List

from bson import ObjectId
from celery import group

from app.celery_app import celery_app
from app.models.entities.build_sample import BuildSample
from app.repositories.build_sample import BuildSampleRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.services.extracts.build_log_extractor import BuildLogExtractor
from app.services.extracts.commit_diff_extractor import CommitDiffExtractor
from app.services.extracts.github_discussion_extractor import GitHubDiscussionExtractor
from app.services.extracts.build_log_extractor import BuildLogExtractor
from app.services.extracts.commit_diff_extractor import CommitDiffExtractor
from app.services.extracts.github_discussion_extractor import GitHubDiscussionExtractor
from app.services.extracts.repo_snapshot_extractor import RepoSnapshotExtractor
from app.tasks.base import PipelineTask
from celery import chord
from app.config import settings
import redis
import json

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
    workflow_run_repo = WorkflowRunRepository(self.db)
    build_sample_repo = BuildSampleRepository(self.db)

    workflow_run = workflow_run_repo.find_by_repo_and_run_id(repo_id, workflow_run_id)
    if not workflow_run:
        logger.error(f"WorkflowRunRaw not found for {repo_id} / {workflow_run_id}")
        return {"status": "error", "message": "WorkflowRunRaw not found"}

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
    publish_build_update(repo_id, build_id, "in_progress")

    # Fan-out tasks
    # Fan-out to feature extraction tasks
    # Use chord to ensure finalize is called with results
    header = [
        extract_build_log_features.s(build_id),
        extract_commit_diff_features.s(build_id),
        extract_repo_snapshot_features.s(build_id),
        extract_github_discussion_features.s(build_id),
    ]

    callback = finalize_build_sample.s(build_id)

    chord(header)(callback)

    return {"status": "processing_started", "build_id": build_id}


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_build_log_features",
    queue="data_processing",
)
def extract_build_log_features(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    build_sample_repo = BuildSampleRepository(self.db)
    workflow_run_repo = WorkflowRunRepository(self.db)

    build_sample = build_sample_repo.find_by_id(ObjectId(build_id))
    if not build_sample:
        logger.error(f"BuildSample {build_id} not found")
        return {}

    workflow_run = workflow_run_repo.find_by_repo_and_run_id(
        str(build_sample.repo_id), build_sample.workflow_run_id
    )
    if not workflow_run:
        logger.error(
            f"WorkflowRunRaw not found for {build_sample.repo_id} / {build_sample.workflow_run_id}"
        )
        return {}

    extractor = BuildLogExtractor()
    return extractor.extract(build_sample, workflow_run)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_commit_diff_features",
    queue="data_processing",
)
def extract_commit_diff_features(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    build_sample_repo = BuildSampleRepository(self.db)
    repo_repo = ImportedRepositoryRepository(self.db)

    build_sample = build_sample_repo.find_by_id(ObjectId(build_id))
    if not build_sample:
        logger.error(f"BuildSample {build_id} not found")
        return {}

    repo = repo_repo.find_by_id(str(build_sample.repo_id))
    if not repo:
        logger.error(f"Repository {build_sample.repo_id} not found")
        return {}

    extractor = CommitDiffExtractor(self.db)
    return extractor.extract(build_sample, repo)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_repo_snapshot_features",
    queue="data_processing",
)
def extract_repo_snapshot_features(self: PipelineTask, build_id: str) -> Dict[str, Any]:
    build_sample_repo = BuildSampleRepository(self.db)
    repo_repo = ImportedRepositoryRepository(self.db)

    build_sample = build_sample_repo.find_by_id(ObjectId(build_id))
    if not build_sample:
        logger.error(f"BuildSample {build_id} not found")
        return {}

    repo = repo_repo.find_by_id(str(build_sample.repo_id))
    if not repo:
        logger.error(f"Repository {build_sample.repo_id} not found")
        return {}

    extractor = RepoSnapshotExtractor(self.db)
    return extractor.extract(build_sample, repo)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.extract_github_discussion_features",
    queue="data_processing",
)
def extract_github_discussion_features(
    self: PipelineTask, build_id: str
) -> Dict[str, Any]:
    build_sample_repo = BuildSampleRepository(self.db)
    repo_repo = ImportedRepositoryRepository(self.db)

    build_sample = build_sample_repo.find_by_id(ObjectId(build_id))
    if not build_sample:
        logger.error(f"BuildSample {build_id} not found")
        return {}

    repo = repo_repo.find_by_id(str(build_sample.repo_id))
    if not repo:
        logger.error(f"Repository {build_sample.repo_id} not found")
        return {}

    extractor = GitHubDiscussionExtractor(self.db)
    return extractor.extract(build_sample, repo)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.processing.finalize_build_sample",
    queue="data_processing",
)
def finalize_build_sample(
    self: PipelineTask, results: List[Dict[str, Any]], build_id: str
) -> Dict[str, Any]:
    build_sample_repo = BuildSampleRepository(self.db)
    merged_updates = {}
    errors = []

    for result in results:
        if isinstance(result, dict):
            if "error" in result:
                errors.append(result["error"])
            else:
                merged_updates.update(result)
        elif isinstance(result, Exception):
            errors.append(str(result))

    if errors:
        status = "failed"
        error_message = "; ".join(errors)
        merged_updates["status"] = status
        merged_updates["error_message"] = error_message
    else:
        merged_updates["status"] = "completed"

    build_sample_repo.update_one(build_id, merged_updates)

    # Fetch repo_id for notification
    build = build_sample_repo.find_by_id(ObjectId(build_id))
    if build:
        publish_build_update(str(build.repo_id), build_id, merged_updates["status"])

    return {"status": merged_updates["status"], "build_id": build_id}
