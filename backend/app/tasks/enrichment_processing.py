"""
Version Enrichment Tasks - Chain+Group pattern for parallel feature extraction.

Flow:
1. start_enrichment - Orchestrator: Dispatch ingestion then enrichment
2. start_ingestion_for_version - Run ingestion for repos with selected features
3. dispatch_enrichment_batches - After ingestion, dispatch batch processing
4. process_enrichment_batch - Process a batch of builds for feature extraction
5. finalize_enrichment - Mark version as completed
"""

from app.entities.raw_repository import RawRepository
from app.entities.dataset_repo_config import DatasetRepoConfig
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List

from bson import ObjectId
from celery import chain, chord, group

from app.celery_app import celery_app
from app.config import settings
from app.paths import REPOS_DIR
from app.entities.dataset_build import DatasetBuild
from app.entities.enums import ExtractionStatus
from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.shared import extract_features_for_build
from backend.app.entities.base import PyObjectId

logger = logging.getLogger(__name__)


# Task 1: Orchestrator - starts ingestion then enrichment
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.start_enrichment",
    queue="processing",
)
def start_enrichment(self: PipelineTask, version_id: str) -> Dict[str, Any]:
    """
    Orchestrator: Start ingestion for version, then dispatch enrichment.

    Flow: start_enrichment -> start_ingestion_for_version -> dispatch_enrichment_batches
          -> chord([process_enrichment_batch x N]) -> finalize_enrichment
    """
    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    dataset_repo = DatasetRepository(self.db)
    repo_config_repo = DatasetRepoConfigRepository(self.db)

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

        # Get repos for this dataset - extract IDs to pass to next tasks
        repo_configs = repo_config_repo.find_by_dataset(version.dataset_id)
        repo_config_ids = [str(rc.id) for rc in repo_configs]

        version_repo.update_one(
            version_id,
            {
                "total_rows": total_rows,
                "repos_total": len(repo_configs),
                "ingestion_status": "ingesting",
            },
        )
        logger.info(
            f"Found {total_rows} validated builds, {len(repo_configs)} repos to ingest"
        )

        # Dispatch ingestion first, then enrichment
        # Pass repo_config_ids to avoid re-querying DB
        workflow = chain(
            start_ingestion_for_version.s(
                version_id=version_id,
                dataset_id=str(version.dataset_id),
                repo_config_ids=repo_config_ids,
            ),
            dispatch_enrichment_batches.si(version_id=version_id),
        )
        workflow.apply_async()

        return {
            "status": "dispatched",
            "total_builds": total_rows,
            "repos": len(repo_configs),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Version enrichment start failed: {error_msg}")
        version_repo.mark_failed(version_id, error_msg)
        raise


# Task 1b: Run ingestion for version repos
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.start_ingestion_for_version",
    queue="ingestion",
    soft_time_limit=600,
    time_limit=900,
)
def start_ingestion_for_version(
    self: PipelineTask,
    version_id: str,
    dataset_id: str,
    repo_config_ids: List[str],
) -> Dict[str, Any]:
    """
    Run ingestion for all repos in a version with selected features.

    Args:
        version_id: DatasetVersion ID
        dataset_id: Dataset ID (passed from caller to avoid re-query)
        repo_config_ids: List of DatasetRepoConfig IDs (passed from caller)

    This is a synchronous task that dispatches per-repo ingestion tasks
    and waits for them to complete before returning.
    """
    from app.tasks.dataset_ingestion import ingest_dataset_builds
    from bson import ObjectId

    version_repo = DatasetVersionRepository(self.db)
    repo_config_repo = DatasetRepoConfigRepository(self.db)
    build_repo = DatasetBuildRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        raise ValueError(f"Version {version_id} not found")

    if not repo_config_ids:
        version_repo.update_one(
            version_id,
            {"ingestion_status": "completed", "ingestion_progress": 100},
        )
        return {"status": "completed", "message": "No repos to ingest"}

    repos_ingested = 0
    repos_failed = 0

    for i, repo_config_id in enumerate(repo_config_ids):
        # Lookup repo_config by ID (single query, not full dataset scan)
        repo_config = repo_config_repo.find_by_id(repo_config_id)
        if not repo_config:
            logger.warning(f"RepoConfig {repo_config_id} not found, skipping")
            continue

        raw_repo_id = str(repo_config.raw_repo_id)

        # Get validated builds for this repo
        builds = build_repo.find_found_builds_by_repo(dataset_id, raw_repo_id)
        build_csv_ids = [str(b.build_id_from_csv) for b in builds]

        if not build_csv_ids:
            continue

        try:
            # Run ingestion synchronously for this repo
            result = ingest_dataset_builds.apply(
                kwargs={
                    "repo_config_id": str(repo_config.id),
                    "build_csv_ids": build_csv_ids,
                    "features": version.selected_features,
                }
            )

            if result.successful():
                repos_ingested += 1
            else:
                repos_failed += 1
                logger.error(
                    f"Ingestion failed for repo {repo_config.normalized_full_name}"
                )

        except Exception as e:
            repos_failed += 1
            logger.error(
                f"Ingestion error for repo {repo_config.normalized_full_name}: {e}"
            )

        # Update progress
        progress = int(((i + 1) / len(repo_config_ids)) * 100)
        version_repo.update_one(
            version_id,
            {
                "ingestion_progress": progress,
                "repos_ingested": repos_ingested,
                "repos_failed": repos_failed,
            },
        )

    # Mark ingestion complete
    version_repo.update_one(
        version_id,
        {"ingestion_status": "completed", "ingestion_progress": 100},
    )

    logger.info(
        f"Ingestion completed for version {version_id}: "
        f"{repos_ingested} succeeded, {repos_failed} failed"
    )

    return {
        "status": "completed",
        "repos_ingested": repos_ingested,
        "repos_failed": repos_failed,
    }


# Task 1c: Dispatch enrichment batches after ingestion
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.dispatch_enrichment_batches",
    queue="processing",
)
def dispatch_enrichment_batches(self: PipelineTask, version_id: str) -> Dict[str, Any]:
    """
    After ingestion completes, dispatch enrichment batches grouped by raw_repo_id.

    Uses dataset.validated_raw_repo_ids for repo grouping.
    Within each repo, splits builds into chunks of ENRICHMENT_BATCH_SIZE.
    """
    version_repo = DatasetVersionRepository(self.db)
    dataset_repo = DatasetRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        raise ValueError(f"Version {version_id} not found")

    # Get validated_raw_repo_ids from dataset (set during save_repos)
    dataset = dataset_repo.find_by_id(version.dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {version.dataset_id} not found")

    validated_raw_repo_ids = dataset.validated_raw_repo_ids or []
    if not validated_raw_repo_ids:
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No validated repos to process"}

    # Batch settings
    batch_size = settings.ENRICHMENT_BATCH_SIZE
    batch_tasks = []
    total_builds = 0

    # For each repo, get builds and split into batches
    for raw_repo_id in validated_raw_repo_ids:
        # Get validated builds for this repo (status='found')
        builds = dataset_build_repo.find_found_builds_by_repo(
            version.dataset_id, str(raw_repo_id)
        )
        if not builds:
            continue

        build_ids = [str(b.id) for b in builds]
        total_builds += len(build_ids)

        # Split into chunks of batch_size
        for i in range(0, len(build_ids), batch_size):
            chunk = build_ids[i : i + batch_size]
            batch_tasks.append(
                process_enrichment_batch.s(
                    version_id=version_id,
                    raw_repo_id=str(raw_repo_id),
                    validated_build_ids=chunk,
                    selected_features=version.selected_features,
                    batch_index=len(batch_tasks),
                    total_batches=0,  # Will be updated after loop
                )
            )

    if not batch_tasks:
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No builds to process"}

    # Update total_batches in each task signature (workaround for immutable signatures)
    total_batches = len(batch_tasks)
    logger.info(
        f"Dispatching {total_batches} batches ({total_builds} builds) for version {version_id}"
    )

    # Use chord to run all batches in parallel, then finalize
    chord(group(batch_tasks))(finalize_enrichment.s(version_id=version_id))

    return {
        "status": "dispatched",
        "batches": total_batches,
        "repos": len(validated_raw_repo_ids),
        "total_builds": total_builds,
    }


# Task 2: Process batch
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.process_enrichment_batch",
    queue="processing",
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
    raw_repo_id: str,
    validated_build_ids: List[str],
    selected_features: List[str],
    batch_index: int,
    total_batches: int,
) -> Dict[str, Any]:
    """
    Process a batch of validated builds for ONE repo.

    Args:
        version_id: DatasetVersion ID
        raw_repo_id: RawRepository ID (all builds in this batch belong to this repo)
        validated_build_ids: List of DatasetBuild IDs to process
        selected_features: Features to extract
        batch_index: Current batch number
        total_batches: Total number of batches

    Returns stats for this batch to be aggregated by finalize_enrichment.
    """
    version_repo = DatasetVersionRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)
    enrichment_build = DatasetEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    repo_config_repo = DatasetRepoConfigRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    version = version_repo.find_by_id(version_id)
    if not version:
        return {"status": "error", "error": "Version not found"}

    # Lookup RawRepository once for this batch
    raw_repo = raw_repo_repo.find_by_id(raw_repo_id)
    if not raw_repo:
        logger.error(f"RawRepository {raw_repo_id} not found")
        return {"status": "error", "error": "RawRepository not found"}

    # Find DatasetRepoConfig by raw_repo_id
    repo_config = repo_config_repo.find_by_dataset_and_repo(
        ObjectId(version.dataset_id), ObjectId(raw_repo_id)
    )
    if not repo_config:
        logger.error(f"DatasetRepoConfig not found for raw_repo {raw_repo_id}")
        return {"status": "error", "error": "DatasetRepoConfig not found"}

    enriched = 0
    failed = 0

    for build_id in validated_build_ids:
        build = dataset_build_repo.find_by_id(build_id)
        if not build:
            logger.warning(f"Build {build_id} not found")
            failed += 1
            continue

        enrichment_build_id = None
        try:
            existing = enrichment_build.find_by_dataset_build_id(
                ObjectId(version.dataset_id), build.id
            )

            if existing:
                enrichment_build_id = str(existing.id)
            else:
                # Create pending build using raw_repo_id from batch params
                new_build = DatasetEnrichmentBuild(
                    _id=None,
                    raw_repo_id=ObjectId(raw_repo_id),
                    raw_build_run_id=ObjectId(build.workflow_run_id),
                    dataset_id=ObjectId(version.dataset_id),
                    dataset_version_id=ObjectId(version_id),
                    dataset_repo_config_id=repo_config.id,
                    dataset_build_id=build.id,
                    extraction_status=ExtractionStatus.PENDING,
                    extraction_error=None,
                    features={},
                    enriched_at=None,
                )
                saved_build = enrichment_build.insert_one(new_build)
                enrichment_build_id = str(saved_build.id)

            # 2. Extract Features using passed repo_config and raw_repo
            result = _extract_features_for_enrichment(
                db=self.db,
                build=build,
                selected_features=selected_features,
                raw_build_run_repo=raw_build_run_repo,
                repo_config=repo_config,
                raw_repo=raw_repo,
            )

            # Determine extraction status from result
            if result["status"] == "completed":
                extraction_status = ExtractionStatus.COMPLETED
            elif result["status"] == "failed":
                extraction_status = ExtractionStatus.FAILED
            else:
                extraction_status = ExtractionStatus.PENDING

            features = result["features"]
            extraction_error = result["errors"][0] if result["errors"] else None

            # 3. Update EnrichmentBuild with results
            # enrichment_build.save_features(
            #     enrichment_build_id,
            #     features,
            # )
            # enrichment_build.update_extraction_status(
            #     enrichment_build_id,
            #     extraction_status,
            #     error=extraction_error,
            # )
            enrichment_build.update_one(
                enrichment_build_id,
                {
                    "extraction_status": extraction_status,
                    "extraction_error": extraction_error,
                    "features": features,
                    "enriched_at": datetime.now(),
                },
            )

            if result["status"] == "completed":
                enriched += 1
            else:
                failed += 1

        except Exception as e:
            logger.warning(f"Failed to enrich build {build.build_id_from_csv}: {e}")
            enrichment_build.update_extraction_status(
                ObjectId(enrichment_build_id),
                ExtractionStatus.FAILED,
                error=str(e),
            )
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
        "total": len(validated_build_ids),
    }


# Task 3: Finalize
@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.version_enrichment.finalize_enrichment",
    queue="processing",
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


def _extract_features_for_enrichment(
    db,
    build: DatasetBuild,
    selected_features: List[str],
    raw_build_run_repo: RawBuildRunRepository,
    repo_config: DatasetRepoConfig,
    raw_repo: RawRepository,
) -> Dict[str, Any]:
    """
    Extract features for a single build using shared helper.

    Args:
        db: Database connection
        build: DatasetBuild entity
        selected_features: Features to extract
        raw_build_run_repo: Repository for RawBuildRun lookup
        repo_config: DatasetRepoConfig (passed from caller, no lookup needed)
        raw_repo: RawRepository (passed from caller, no lookup needed)

    Returns result dict with status, features, errors, warnings.
    """
    if not build.workflow_run_id:
        logger.warning(f"Build {build.build_id_from_csv} has no workflow_run_id")
        return {
            "status": "failed",
            "features": {},
            "errors": ["No workflow_run_id"],
            "warnings": [],
        }

    raw_build_run = raw_build_run_repo.find_by_id(str(build.workflow_run_id))
    if not raw_build_run:
        logger.warning(f"RawBuildRun {build.workflow_run_id} not found")
        return {
            "status": "failed",
            "features": {},
            "errors": ["RawBuildRun not found"],
            "warnings": [],
        }

    # Use shared helper for feature extraction (returns full result with status)
    return extract_features_for_build(
        db=db,
        raw_repo=raw_repo,
        repo_config=repo_config,
        raw_build_run=raw_build_run,
        selected_features=selected_features,
    )
