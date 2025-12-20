"""
Version Enrichment Tasks - Chain+Group pattern for parallel feature extraction.

Flow:
1. start_enrichment - Orchestrator: Dispatch ingestion then enrichment
2. start_ingestion_for_version - Run ingestion for repos with selected features
3. dispatch_enrichment_batches - After ingestion, dispatch batch processing
4. process_enrichment_batch - Process a batch of builds for feature extraction
5. finalize_enrichment - Mark version as completed
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId
from celery import chain, chord, group

from app.celery_app import celery_app
from app.config import settings
from app.entities.dataset_build import DatasetBuild
from app.entities.dataset_enrichment_build import DatasetEnrichmentBuild
from app.entities.dataset_version import DatasetVersion
from app.entities.enums import ExtractionStatus
from app.entities.raw_repository import RawRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.tasks.base import PipelineTask
from app.tasks.shared import extract_features_for_build

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

    # Load version
    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        logger.error(f"Version {version_id} not found")
        return {"status": "error", "error": "Version not found"}

    # Mark as started
    version_repo.mark_started(version_id, task_id=self.request.id)

    try:
        # Load dataset
        dataset = dataset_repo.find_by_id(dataset_version.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_version.dataset_id} not found")

        # Get validated builds
        validated_builds = dataset_build_repo.find_validated_builds(dataset_version.dataset_id)

        total_rows = len(validated_builds)
        if total_rows == 0:
            raise ValueError("No validated builds found. Please run validation first.")

        # Get validated repos from dataset (replaces DatasetRepoConfig)
        validated_raw_repo_ids = list(dataset.repo_ci_providers.keys())

        version_repo.update_one(
            version_id,
            {
                "total_rows": total_rows,
                "repos_total": len(validated_raw_repo_ids),
                "ingestion_status": "ingesting",
            },
        )
        logger.info(
            f"Found {total_rows} validated builds, "
            f"{len(validated_raw_repo_ids)} repos to ingest"
        )

        # Dispatch ingestion first, then enrichment
        # Pass raw_repo_ids from repo_ci_providers
        workflow = chain(
            start_ingestion_for_version.s(
                version_id=version_id,
                dataset_id=str(dataset_version.dataset_id),
                raw_repo_ids=[str(repo_id) for repo_id in validated_raw_repo_ids],
            ),
            dispatch_enrichment_batches.si(version_id=version_id),
        )
        workflow.apply_async()

        return {
            "status": "dispatched",
            "total_builds": total_rows,
            "repos": len(validated_raw_repo_ids),
        }

    except Exception as exc:
        error_msg = str(exc)
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
    raw_repo_ids: List[str],
) -> Dict[str, Any]:
    """
    Run ingestion for all repos in a version with selected features.

    Args:
        version_id: DatasetVersion ID
        dataset_id: Dataset ID (passed from caller to avoid re-query)
        raw_repo_ids: List of RawRepository IDs (from dataset.repo_ci_providers.keys())

    This is a synchronous task that dispatches per-repo ingestion tasks
    and waits for them to complete before returning.
    """
    from app.tasks.dataset_ingestion import ingest_dataset_builds_for_repo

    version_repo = DatasetVersionRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)

    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        raise ValueError(f"Version {version_id} not found")

    if not raw_repo_ids:
        version_repo.update_one(
            version_id,
            {"ingestion_status": "completed", "ingestion_progress": 100},
        )
        return {"status": "completed", "message": "No repos to ingest"}

    repos_ingested = 0
    repos_failed = 0

    for idx, raw_repo_id in enumerate(raw_repo_ids):
        # Lookup RawRepository by ID
        raw_repo = raw_repo_repo.find_by_id(raw_repo_id)
        if not raw_repo:
            logger.warning(f"RawRepository {raw_repo_id} not found, skipping")
            repos_failed += 1
            continue

        # Get validated builds for this repo
        dataset_builds = dataset_build_repo.find_found_builds_by_repo(dataset_id, raw_repo_id)
        build_csv_ids = [str(build.build_id_from_csv) for build in dataset_builds]

        if not build_csv_ids:
            continue

        try:
            # Run ingestion synchronously for this repo
            ingestion_result = ingest_dataset_builds_for_repo.apply(
                kwargs={
                    "version_id": version_id,
                    "raw_repo_id": raw_repo_id,
                    "build_csv_ids": build_csv_ids,
                    "features": dataset_version.selected_features,
                }
            )

            if ingestion_result.successful():
                repos_ingested += 1
            else:
                repos_failed += 1
                logger.error(f"Ingestion failed for repo {raw_repo.full_name}")

        except Exception as exc:
            repos_failed += 1
            logger.error(f"Ingestion error for repo {raw_repo.full_name}: {exc}")

        # Update progress
        progress = int(((idx + 1) / len(raw_repo_ids)) * 100)
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

    Uses dataset.repo_ci_providers.keys() for repo grouping.
    Within each repo, splits builds into chunks of ENRICHMENT_BATCH_SIZE.
    """
    version_repo = DatasetVersionRepository(self.db)
    dataset_repo = DatasetRepository(self.db)
    dataset_build_repo = DatasetBuildRepository(self.db)

    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        raise ValueError(f"Version {version_id} not found")

    # Get validated repo IDs from dataset (set during save_repos)
    dataset = dataset_repo.find_by_id(dataset_version.dataset_id)
    if not dataset:
        raise ValueError(f"Dataset {dataset_version.dataset_id} not found")

    # Use repo_ci_providers keys as validated repo IDs
    validated_raw_repo_ids = list(dataset.repo_ci_providers.keys())
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
        dataset_builds = dataset_build_repo.find_found_builds_by_repo(
            dataset_version.dataset_id, str(raw_repo_id)
        )
        if not dataset_builds:
            continue

        build_ids = [str(build.id) for build in dataset_builds]
        total_builds += len(build_ids)

        # Split into chunks of batch_size
        for chunk_start in range(0, len(build_ids), batch_size):
            chunk = build_ids[chunk_start : chunk_start + batch_size]
            batch_tasks.append(
                process_enrichment_batch.s(
                    version_id=version_id,
                    raw_repo_id=str(raw_repo_id),
                    validated_build_ids=chunk,
                    selected_features=dataset_version.selected_features,
                    batch_index=len(batch_tasks),
                    total_batches=0,  # Will be updated after loop
                )
            )

    if not batch_tasks:
        version_repo.mark_completed(version_id)
        return {"status": "completed", "message": "No builds to process"}

    # Log dispatch info
    total_batches = len(batch_tasks)
    logger.info(
        f"Dispatching {total_batches} batches ({total_builds} builds) " f"for version {version_id}"
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
    enrichment_build_repo = DatasetEnrichmentBuildRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)

    dataset_version = version_repo.find_by_id(version_id)
    if not dataset_version:
        return {"status": "error", "error": "Version not found"}

    # Lookup RawRepository once for this batch
    raw_repo = raw_repo_repo.find_by_id(raw_repo_id)
    if not raw_repo:
        logger.error(f"RawRepository {raw_repo_id} not found")
        return {"status": "error", "error": "RawRepository not found"}

    enriched_count = 0
    failed_count = 0

    for dataset_build_id in validated_build_ids:
        dataset_build = dataset_build_repo.find_by_id(dataset_build_id)
        if not dataset_build:
            logger.warning(f"Build {dataset_build_id} not found")
            failed_count += 1
            continue

        enrichment_build_id = None
        try:
            existing_enrichment = enrichment_build_repo.find_by_dataset_build_id(
                ObjectId(dataset_version.dataset_id), dataset_build.id
            )

            if existing_enrichment:
                enrichment_build_id = str(existing_enrichment.id)
            else:
                # Create pending build using raw_repo_id from batch params
                new_enrichment_build = DatasetEnrichmentBuild(
                    _id=None,
                    raw_repo_id=ObjectId(raw_repo_id),
                    raw_build_run_id=ObjectId(dataset_build.workflow_run_id),
                    dataset_id=ObjectId(dataset_version.dataset_id),
                    dataset_version_id=ObjectId(version_id),
                    dataset_build_id=dataset_build.id,
                    extraction_status=ExtractionStatus.PENDING,
                    extraction_error=None,
                    features={},
                    enriched_at=None,
                )
                saved_enrichment = enrichment_build_repo.insert_one(new_enrichment_build)
                enrichment_build_id = str(saved_enrichment.id)

            # Extract Features using DatasetVersion for config
            extraction_result = _extract_features_for_enrichment(
                db=self.db,
                dataset_build=dataset_build,
                selected_features=selected_features,
                raw_build_run_repo=raw_build_run_repo,
                dataset_version=dataset_version,
                raw_repo=raw_repo,
            )

            # Determine extraction status from result
            if extraction_result["status"] == "completed":
                extraction_status = ExtractionStatus.COMPLETED
            elif extraction_result["status"] == "partial":
                extraction_status = ExtractionStatus.PARTIAL
            elif extraction_result["status"] == "failed":
                extraction_status = ExtractionStatus.FAILED
            else:
                extraction_status = ExtractionStatus.PENDING

            extracted_features = extraction_result["features"]
            extraction_error = (
                extraction_result["errors"][0] if extraction_result["errors"] else None
            )

            # Build update dict with Graceful Degradation tracking
            update_data = {
                "extraction_status": extraction_status,
                "extraction_error": extraction_error,
                "features": extracted_features,
                "enriched_at": datetime.now(),
            }

            # Track missing resources and skipped features
            if extraction_result.get("missing_resources"):
                update_data["missing_resources"] = extraction_result["missing_resources"]
            if extraction_result.get("skipped_features"):
                update_data["skipped_features"] = extraction_result["skipped_features"]

            enrichment_build_repo.update_one(enrichment_build_id, update_data)

            if extraction_result["status"] == "completed":
                enriched_count += 1
            else:
                failed_count += 1

        except Exception as exc:
            logger.warning(f"Failed to enrich build {dataset_build.build_id_from_csv}: {exc}")
            enrichment_build_repo.update_extraction_status(
                ObjectId(enrichment_build_id),
                ExtractionStatus.FAILED,
                error=str(exc),
            )
            failed_count += 1

    logger.info(
        f"Batch {batch_index + 1}/{total_batches} completed: "
        f"{enriched_count} enriched, {failed_count} failed"
    )

    return {
        "batch_index": batch_index,
        "status": "completed",
        "enriched": enriched_count,
        "failed": failed_count,
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

    for batch_result in batch_results:
        total_enriched += batch_result.get("enriched", 0)
        total_failed += batch_result.get("failed", 0)
        total_processed += batch_result.get("total", 0)

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
    dataset_build: DatasetBuild,
    selected_features: List[str],
    raw_build_run_repo: RawBuildRunRepository,
    dataset_version: DatasetVersion,
    raw_repo: RawRepository,
) -> Dict[str, Any]:
    """
    Extract features for a single build using shared helper.

    Args:
        db: Database connection
        dataset_build: DatasetBuild entity
        selected_features: Features to extract
        raw_build_run_repo: Repository for RawBuildRun lookup
        dataset_version: DatasetVersion entity (used for config via feature_configs)
        raw_repo: RawRepository (passed from caller, no lookup needed)

    Returns result dict with status, features, errors, warnings.
    """
    if not dataset_build.workflow_run_id:
        logger.warning(f"Build {dataset_build.build_id_from_csv} has no workflow_run_id")
        return {
            "status": "failed",
            "features": {},
            "errors": ["No workflow_run_id"],
            "warnings": [],
        }

    raw_build_run = raw_build_run_repo.find_by_id(str(dataset_build.workflow_run_id))
    if not raw_build_run:
        logger.warning(f"RawBuildRun {dataset_build.workflow_run_id} not found")
        return {
            "status": "failed",
            "features": {},
            "errors": ["RawBuildRun not found"],
            "warnings": [],
        }

    # Use shared helper for feature extraction
    # DatasetVersion inherits from FeatureConfigBase, so it works as config source
    return extract_features_for_build(
        db=db,
        raw_repo=raw_repo,
        repo_config=dataset_version,  # DatasetVersion now has feature_configs
        raw_build_run=raw_build_run,
        selected_features=selected_features,
    )
