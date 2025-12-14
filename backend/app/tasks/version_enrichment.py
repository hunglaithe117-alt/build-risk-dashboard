"""
Version Enrichment Tasks - Chain+Group pattern for parallel feature extraction.

Flow:
1. start_enrichment - Orchestrator: Query builds, dispatch batches
2. process_enrichment_batch - Process a batch of builds for feature extraction
3. finalize_enrichment - Mark version as completed
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.config import settings
from app.database.mongo import get_database
from app.entities.dataset_build import DatasetBuild
from app.entities.dataset_version import VersionStatus
from app.entities.enums import ExtractionStatus
from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from backend.app.repositories.raw_build_run import RawWorkflowRunRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.pipeline.hamilton_runner import HamiltonPipeline
from app.pipeline.hamilton_features._inputs import build_hamilton_inputs
from app.pipeline.core.registry import feature_registry
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)


# Task 1: Orchestrator
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.start_enrichment",
    queue="enrichment",
)
def start_enrichment(self: PipelineTask, version_id: str) -> Dict[str, Any]:
    """
    Orchestrator: Query validated builds and dispatch enrichment batches.

    Flow: start_enrichment -> chord(group([process_enrichment_batch x N]), finalize_enrichment)
    """
    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    dataset_repo = DatasetRepository(self.db)

    # Load version
    version = version_repo.find_by_id(version_id)
    if not version:
        logger.error(f"Version {version_id} not found")
        return {"status": "error", "error": "Version not found"}

    # Mark as started
    version_repo.mark_started(version_id, task_id=self.request.id)

    try:
        # Load dataset
        dataset = dataset_repo.find_by_id(version.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {version.dataset_id} not found")

        # Get validated builds
        validated_builds = dataset_build_repo.find_validated_builds(version.dataset_id)

        total_rows = len(validated_builds)
        if total_rows == 0:
            raise ValueError("No validated builds found. Please run validation first.")

        version_repo.update_one(version_id, {"total_rows": total_rows})
        logger.info(f"Found {total_rows} validated builds to process")

        # Get build IDs to process
        build_ids = [str(build.id) for build in validated_builds]

        # Split into batches
        batch_size = settings.ENRICHMENT_BATCH_SIZE
        batches = [
            build_ids[i : i + batch_size] for i in range(0, len(build_ids), batch_size)
        ]

        logger.info(
            f"Dispatching {len(batches)} batches of {batch_size} builds for enrichment"
        )

        # Create tasks for each batch
        batch_tasks = [
            process_enrichment_batch.s(
                version_id=version_id,
                build_ids=batch,
                selected_features=version.selected_features,
                batch_index=i,
                total_batches=len(batches),
            )
            for i, batch in enumerate(batches)
        ]

        # Use chord to run all batches in parallel,
        # then finalize when all complete
        workflow = chord(group(batch_tasks))(
            finalize_enrichment.s(version_id=version_id)
        )

        return {
            "status": "dispatched",
            "total_builds": total_rows,
            "batches": len(batches),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Version enrichment start failed: {error_msg}")
        version_repo.mark_failed(version_id, error_msg)
        raise


# Task 2: Process batch
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.process_enrichment_batch",
    queue="enrichment",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": settings.ENRICHMENT_MAX_RETRIES},
    retry_backoff=True,
    retry_backoff_max=600,
    soft_time_limit=600,
    time_limit=900,
)
def process_enrichment_batch(
    self: PipelineTask,
    version_id: str,
    build_ids: List[str],
    selected_features: List[str],
    batch_index: int,
    total_batches: int,
) -> Dict[str, Any]:
    """
    Process a batch of builds for feature extraction.

    Returns stats for this batch to be aggregated by finalize_enrichment.
    """
    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)
    workflow_run_repo = RawWorkflowRunRepository(self.db)
    enrichment_repo_repo = DatasetRepoConfigRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        return {"status": "error", "error": "Version not found"}

    enriched = 0
    failed = 0

    for build_id in build_ids:
        build = dataset_build_repo.find_by_id(build_id)
        if not build:
            logger.warning(f"Build {build_id} not found")
            failed += 1
            continue

        try:
            features = _extract_features_for_build(
                db=self.db,
                build=build,
                version_id=version_id,
                selected_features=selected_features,
                workflow_run_repo=workflow_run_repo,
                enrichment_repo_repo=enrichment_repo_repo,
                enrichment_build_repo=enrichment_build_repo,
                raw_repo_repo=raw_repo_repo,
            )

            # Update or create enrichment_build
            existing = enrichment_build_repo.find_by_build_id_and_dataset(
                build.build_id_from_csv, version.dataset_id
            )
            if existing:
                enrichment_build_repo.update_one(
                    str(existing.id),
                    {
                        "features": features,
                        "extraction_status": ExtractionStatus.COMPLETED,
                        "version_id": ObjectId(version_id),
                    },
                )
            else:
                enrichment_build = DatasetEnrichmentBuild(
                    repo_id=build.repo_id,
                    enrichment_repo_id=build.repo_id,
                    dataset_id=ObjectId(version.dataset_id),
                    version_id=ObjectId(version_id),
                    build_id_from_csv=build.build_id_from_csv,
                    extraction_status=ExtractionStatus.COMPLETED,
                    features=features,
                )
                enrichment_build_repo.insert_one(enrichment_build)

            enriched += 1

        except Exception as e:
            logger.warning(f"Failed to enrich build {build.build_id_from_csv}: {e}")

            existing = enrichment_build_repo.find_by_build_id_and_dataset(
                build.build_id_from_csv, version.dataset_id
            )
            if not existing:
                enrichment_build = DatasetEnrichmentBuild(
                    repo_id=build.repo_id,
                    enrichment_repo_id=build.repo_id,
                    dataset_id=ObjectId(version.dataset_id),
                    version_id=ObjectId(version_id),
                    build_id_from_csv=build.build_id_from_csv,
                    extraction_status=ExtractionStatus.FAILED,
                    error_message=str(e),
                    features={},
                )
                enrichment_build_repo.insert_one(enrichment_build)

            failed += 1

    logger.info(
        f"Batch {batch_index + 1}/{total_batches} completed: "
        f"{enriched} enriched, {failed} failed"
    )

    return {
        "batch_index": batch_index,
        "status": "completed",
        "enriched": enriched,
        "failed": failed,
        "total": len(build_ids),
    }


# Task 3: Finalize
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.finalize_enrichment",
    queue="enrichment",
)
def finalize_enrichment(
    self: PipelineTask,
    batch_results: List[Dict[str, Any]],
    version_id: str,
) -> Dict[str, Any]:
    """
    Aggregate results from all batch enrichments and update version status.
    """
    version_repo = DatasetVersionRepository(self.db)

    # Aggregate stats
    total_enriched = 0
    total_failed = 0
    total_processed = 0

    for result in batch_results:
        total_enriched += result.get("enriched", 0)
        total_failed += result.get("failed", 0)
        total_processed += result.get("total", 0)

    # Update final progress
    version_repo.update_progress(
        version_id,
        processed_rows=total_processed,
        enriched_rows=total_enriched,
        failed_rows=total_failed,
    )

    # Mark completed
    version_repo.mark_completed(version_id)

    logger.info(
        f"Version enrichment completed: {version_id}, "
        f"{total_enriched}/{total_processed} rows enriched"
    )

    return {
        "status": "completed",
        "version_id": version_id,
        "enriched_rows": total_enriched,
        "failed_rows": total_failed,
        "total_rows": total_processed,
    }


def _extract_features_for_build(
    db,
    build: DatasetBuild,
    version_id: str,
    selected_features: List[str],
    workflow_run_repo: RawWorkflowRunRepository,
    enrichment_repo_repo: DatasetRepoConfigRepository,
    enrichment_build_repo: DatasetEnrichmentBuildRepository,
    raw_repo_repo: RawRepositoryRepository,
) -> Dict[str, Any]:
    """Extract features for a single build using HamiltonPipeline."""
    if not build.workflow_run_id:
        logger.warning(f"Build {build.build_id_from_csv} has no workflow_run_id")
        return {name: None for name in selected_features}

    workflow_run = workflow_run_repo.find_by_id(str(build.workflow_run_id))

    if not workflow_run:
        logger.warning(f"WorkflowRun {build.workflow_run_id} not found")
        return {name: None for name in selected_features}

    enrichment_repo = enrichment_repo_repo.find_by_id(str(build.repo_id))

    if not enrichment_repo:
        logger.warning(f"EnrichmentRepo {build.repo_id} not found")
        return {name: None for name in selected_features}

    # Fetch RawRepository
    raw_repo = raw_repo_repo.find_by_id(str(build.repo_id))
    if not raw_repo:
        logger.warning(f"RawRepository {build.repo_id} not found")
        return {name: None for name in selected_features}

    # Check if already exists
    existing_build = enrichment_build_repo.find_by_build_id_and_dataset(
        build.build_id_from_csv, str(build.dataset_id)
    )

    if existing_build:
        enrichment_build = existing_build
    else:
        enrichment_build = DatasetEnrichmentBuild(
            repo_id=build.repo_id,
            workflow_run_id=workflow_run.workflow_run_id,
            head_sha=workflow_run.head_sha,
            build_number=workflow_run.run_number,
            build_created_at=workflow_run.ci_created_at,
            enrichment_repo_id=enrichment_repo.id,
            dataset_id=build.dataset_id,
            version_id=ObjectId(version_id),
            build_id_from_csv=build.build_id_from_csv,
            extraction_status=ExtractionStatus.PENDING,
        )
        enrichment_build = enrichment_build_repo.insert_one(enrichment_build)

    try:
        # Build paths for git operations
        repos_dir = Path(settings.REPO_MIRROR_ROOT) / "repos"
        repo_path = repos_dir / str(build.repo_id)

        # Build all Hamilton inputs using helper function
        inputs = build_hamilton_inputs(
            raw_repo=raw_repo,
            repo_config=enrichment_repo,
            workflow_run=workflow_run,
            repo_path=repo_path,
        )

        # Execute Hamilton pipeline
        pipeline = HamiltonPipeline(db=db)

        features = pipeline.run(
            git_history=inputs.git_history,
            git_worktree=inputs.git_worktree,
            repo=inputs.repo,
            workflow_run=inputs.workflow_run,
            repo_config=inputs.repo_config,
            github_client=None,
            features_filter=set(selected_features) if selected_features else None,
        )

        formatted_features = feature_registry.format_features_for_storage(features)

        logger.debug(
            f"Extracted {len(formatted_features)} features for build {build.build_id_from_csv}"
        )

        return formatted_features

    except Exception as e:
        logger.error(
            f"Pipeline failed for build {build.build_id_from_csv}: {e}",
            exc_info=True,
        )
        return {name: None for name in selected_features}
