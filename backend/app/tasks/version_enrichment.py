"""
Version Enrichment Task - Extract features for validated builds.

Flow:
1. Query dataset_builds (status=FOUND) to get validated builds
2. For each build, run feature extraction pipeline
3. Save features to enrichment_builds collection (DB)
4. Export all features to Parquet file for download
"""

from app.repositories.dataset_repository import DatasetRepository
from pymongo.synchronous.database import Database
from app.entities.dataset_build import DatasetBuild
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.database.mongo import get_database
from app.entities.dataset_version import VersionStatus
from app.entities.base_build import ExtractionStatus
from app.entities.enrichment_build import EnrichmentBuild
from app.repositories.dataset_version import DatasetVersionRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.enrichment_build import EnrichmentBuildRepository
from app.entities.enrichment_build import EnrichmentBuild
from app.repositories.workflow_run import WorkflowRunRepository
from app.repositories.enrichment_repository import EnrichmentRepositoryRepository
from app.pipeline.runner import FeaturePipeline
from app.pipeline.core.registry import feature_registry

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.version_enrichment.enrich_version_task",
    queue="enrichment",
    soft_time_limit=7200,  # 2 hours
    time_limit=7500,  # 2.5 hours hard limit
)
def enrich_version_task(self, version_id: str):
    logger.info(f"Starting version enrichment task for {version_id}")

    db = get_database()
    version_repo = DatasetVersionRepository(db)
    dataset_build_repo = DatasetBuildRepository(db)
    enrichment_build_repo = EnrichmentBuildRepository(db)
    dataset_repo = DatasetRepository(db)

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

        validated_builds = dataset_build_repo.find_validated_builds(version.dataset_id)

        total_rows = len(validated_builds)
        if total_rows == 0:
            raise ValueError("No validated builds found. Please run validation first.")

        version_repo.update_one(version_id, {"total_rows": total_rows})
        logger.info(f"Found {total_rows} validated builds to process")

        # Process rows
        processed = 0
        enriched = 0
        failed = 0
        enriched_data: List[Dict[str, Any]] = []

        for build in validated_builds:
            try:
                features = _extract_features_for_build(
                    db=db,
                    build=build,
                    selected_features=version.selected_features,
                )

                enrichment_build = EnrichmentBuild(
                    repo_id=build.repo_id,
                    enrichment_repo_id=build.repo_id,
                    dataset_id=ObjectId(version.dataset_id),
                    build_id_from_csv=build.build_id_from_csv,
                    extraction_status=ExtractionStatus.COMPLETED,
                    features=features,
                )

                existing = enrichment_build_repo.find_by_build_id_and_dataset(
                    build.build_id_from_csv, version.dataset_id
                )
                if existing:
                    enrichment_build_repo.update_one(
                        str(existing.id),
                        {
                            "features": features,
                            "extraction_status": ExtractionStatus.COMPLETED,
                        },
                    )
                else:
                    enrichment_build_repo.insert_one(enrichment_build)

                # Add to enriched data for Parquet export
                row_data = {
                    "build_id": build.build_id_from_csv,
                    "repo_name": build.repo_name_from_csv,
                    **features,
                }
                enriched_data.append(row_data)

                processed += 1
                enriched += 1

            except Exception as e:
                logger.warning(f"Failed to enrich build {build.build_id_from_csv}: {e}")

                enrichment_build = EnrichmentBuild(
                    repo_id=build.repo_id,
                    enrichment_repo_id=build.repo_id,
                    dataset_id=ObjectId(version.dataset_id),
                    build_id_from_csv=build.build_id_from_csv,
                    extraction_status=ExtractionStatus.FAILED,
                    error_message=str(e),
                    features={},
                )

                existing = enrichment_build_repo.find_by_build_id_and_dataset(
                    build.build_id_from_csv, version.dataset_id
                )
                if not existing:
                    enrichment_build_repo.insert_one(enrichment_build)

                processed += 1
                failed += 1

            if processed % 10 == 0:
                version_repo.update_progress(
                    version_id,
                    processed_rows=processed,
                    enriched_rows=enriched,
                    failed_rows=failed,
                )

        version_repo.update_progress(
            version_id,
            processed_rows=processed,
            enriched_rows=enriched,
            failed_rows=failed,
        )

        output_path, file_size = _export_to_parquet(
            enriched_data=enriched_data,
            dataset_id=version.dataset_id,
            version_number=version.version_number,
        )

        output_filename = os.path.basename(output_path)

        version_repo.mark_completed(
            version_id,
            file_path=output_path,
            file_name=output_filename,
            file_size_bytes=file_size,
        )

        logger.info(
            f"Version enrichment completed: {version_id}, "
            f"{enriched}/{total_rows} rows enriched, "
            f"output: {output_path} ({file_size} bytes)"
        )

        return {
            "status": "completed",
            "version_id": version_id,
            "enriched_rows": enriched,
            "failed_rows": failed,
            "output_file": output_path,
            "file_size_bytes": file_size,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Version enrichment failed: {error_msg}")
        version_repo.mark_failed(version_id, error_msg)

        # Re-raise for Celery retry logic
        raise self.retry(
            exc=e,
            countdown=min(60 * (2**self.request.retries), 1800),
            max_retries=2,
        )


def _extract_features_for_build(
    db: Database,
    build: DatasetBuild,
    selected_features: List[str],
) -> Dict[str, Any]:
    if not build.workflow_run_id:
        logger.warning(f"Build {build.build_id_from_csv} has no workflow_run_id")
        return {name: None for name in selected_features}

    workflow_run_repo = WorkflowRunRepository(db)
    workflow_run = workflow_run_repo.find_by_id(str(build.workflow_run_id))

    if not workflow_run:
        logger.warning(f"WorkflowRun {build.workflow_run_id} not found")
        return {name: None for name in selected_features}

    enrichment_repo_repo = EnrichmentRepositoryRepository(db)
    enrichment_repo = enrichment_repo_repo.find_by_id(str(build.repo_id))

    if not enrichment_repo:
        logger.warning(f"EnrichmentRepo {build.repo_id} not found")
        return {name: None for name in selected_features}

    # Create EnrichmentBuild and save to DB first to get ObjectId
    enrichment_build_repo = EnrichmentBuildRepository(db)

    # Check if already exists
    existing_build = enrichment_build_repo.find_by_build_id_and_dataset(
        build.build_id_from_csv, str(build.dataset_id)
    )

    if existing_build:
        enrichment_build = existing_build
    else:
        enrichment_build = EnrichmentBuild(
            repo_id=build.repo_id,
            workflow_run_id=workflow_run.workflow_run_id,
            head_sha=workflow_run.head_sha,
            build_number=workflow_run.run_number,
            build_created_at=workflow_run.ci_created_at,
            enrichment_repo_id=enrichment_repo.id,
            dataset_id=build.dataset_id,
            build_id_from_csv=build.build_id_from_csv,
            extraction_status=ExtractionStatus.PENDING,
        )
        # Save to DB to get ObjectId
        enrichment_build = enrichment_build_repo.insert_one(enrichment_build)

    try:
        pipeline = FeaturePipeline(
            db=db,
            max_workers=2,
        )

        result = pipeline.run(
            build_sample=enrichment_build,
            repo=enrichment_repo,
            workflow_run=workflow_run,
            parallel=True,
            features_filter=set(selected_features),
        )

        features = feature_registry.format_features_for_storage(
            result.get("features", {})
        )

        logger.debug(
            f"Extracted {len(features)} features for build {build.build_id_from_csv}"
        )

        return features

    except Exception as e:
        logger.error(
            f"Pipeline failed for build {build.build_id_from_csv}: {e}",
            exc_info=True,
        )
        return {name: None for name in selected_features}


def _export_to_parquet(
    enriched_data: List[Dict[str, Any]],
    dataset_id: str,
    version_number: int,
) -> tuple[str, int]:
    import pandas as pd

    output_dir = os.path.join(settings.DATA_DIR, "enriched", dataset_id)
    os.makedirs(output_dir, exist_ok=True)

    output_filename = f"enriched_v{version_number}.parquet"
    output_path = os.path.join(output_dir, output_filename)

    df = pd.DataFrame(enriched_data)

    df.to_parquet(output_path, engine="pyarrow", compression="snappy", index=False)

    file_size = os.path.getsize(output_path)

    logger.info(
        f"Exported {len(enriched_data)} rows to Parquet: {output_path} "
        f"({file_size} bytes, compression=snappy)"
    )

    return output_path, file_size
