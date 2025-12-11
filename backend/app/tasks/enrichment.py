"""
Enrichment Task - Background processing for dataset enrichment.

This task processes CSV rows to:
1. Auto-import missing repositories
2. Create EnrichmentBuild records for each row
3. Run the feature extraction pipeline
4. Save enriched features to database
5. Emit WebSocket progress events
"""

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import redis
from celery import shared_task

from app.database.mongo import get_database
from app.config import settings
from app.entities.enrichment_job import EnrichmentJob
from app.entities.enrichment_build import EnrichmentBuild
from app.entities.enrichment_repository import EnrichmentRepository
from app.entities.workflow_run import WorkflowRunRaw
from app.repositories.enrichment_job import EnrichmentJobRepository
from app.repositories.enrichment_build import EnrichmentBuildRepository
from app.repositories.enrichment_repository import EnrichmentRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.repositories.dataset_repository import DatasetRepository
from app.pipeline.runner import FeaturePipeline
from app.services.github import GitHubClient

logger = logging.getLogger(__name__)

# Redis for WebSocket pub/sub
REDIS_CHANNEL_PREFIX = "enrichment:progress:"


def get_redis_client() -> redis.Redis:
    """Get Redis client for pub/sub."""
    return redis.from_url(settings.REDIS_URL)


def publish_progress(job_id: str, event: Dict[str, Any]) -> None:
    """Publish progress event to Redis for WebSocket delivery."""
    try:
        client = get_redis_client()
        import json

        client.publish(f"{REDIS_CHANNEL_PREFIX}{job_id}", json.dumps(event))
    except Exception as e:
        logger.warning(f"Failed to publish progress event: {e}")


@shared_task(
    name="app.tasks.enrichment.enrich_dataset_task",
    bind=True,
    queue="data_processing",
    soft_time_limit=3600,  # 1 hour soft limit
    time_limit=3900,  # 1 hour 5 min hard limit
)
def enrich_dataset_task(
    self,
    job_id: str,
    dataset_id: str,
    user_id: str,
    selected_features: List[str],
    auto_import_repos: bool = True,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    """
    Main enrichment task - processes CSV rows and extracts features.

    Args:
        job_id: EnrichmentJob ID
        dataset_id: Dataset ID to enrich
        user_id: User ID who started the job
        selected_features: List of feature IDs to extract
        auto_import_repos: Whether to auto-import missing repos
        skip_existing: Whether to skip rows that already have features

    Returns:
        Dict with enrichment results
    """
    db = get_database()
    job_repo = EnrichmentJobRepository(db)
    dataset_repo = DatasetRepository(db)
    enrichment_repo_repo = EnrichmentRepositoryRepository(db)
    enrichment_build_repo = EnrichmentBuildRepository(db)
    workflow_repo = WorkflowRunRepository(db)

    # Mark job as started
    job_repo.mark_started(job_id, celery_task_id=self.request.id)

    try:
        # Load dataset
        dataset = dataset_repo.find_by_id(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Read CSV file
        csv_path = Path(dataset.get("file_path", ""))
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        # Parse mapping
        mapping = dataset.get("mapped_fields", {})
        build_id_col = mapping.get("build_id")
        commit_sha_col = mapping.get("commit_sha")
        repo_name_col = mapping.get("repo_name")

        if not all([build_id_col, repo_name_col]):
            raise ValueError("Required field mapping incomplete (build_id, repo_name)")

        # Read and count rows
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        total_rows = len(rows)
        job_repo.update_one(job_id, {"total_rows": total_rows})

        # Initialize pipeline
        pipeline = FeaturePipeline(db, notify_on_failure=False)

        # Track stats
        processed = 0
        enriched = 0
        failed = 0
        skipped = 0
        repos_imported: Set[str] = set()
        enriched_rows: List[Dict[str, Any]] = []

        # Process each row
        for idx, row in enumerate(rows):
            try:
                repo_name = row.get(repo_name_col, "").strip()
                build_id = row.get(build_id_col, "").strip()
                commit_sha = (
                    row.get(commit_sha_col, "").strip() if commit_sha_col else None
                )

                if not repo_name or not build_id:
                    failed += 1
                    job_repo.update_progress(
                        job_id,
                        processed + 1,
                        enriched,
                        failed,
                        {"row_index": idx, "error": "Missing repo_name or build_id"},
                    )
                    processed += 1
                    continue

                # Check if repo exists for this dataset
                enrichment_repo = enrichment_repo_repo.find_by_dataset_and_full_name(
                    dataset_id, repo_name
                )

                if not enrichment_repo:
                    if auto_import_repos:
                        # Auto-import repo for this dataset
                        enrichment_repo = _auto_import_enrichment_repo(
                            enrichment_repo_repo, dataset_id, repo_name
                        )
                        if enrichment_repo:
                            repos_imported.add(repo_name)
                            job_repo.add_auto_imported_repo(job_id, repo_name)

                    if not enrichment_repo:
                        failed += 1
                        job_repo.update_progress(
                            job_id,
                            processed + 1,
                            enriched,
                            failed,
                            {
                                "row_index": idx,
                                "error": f"Repository not found: {repo_name}",
                            },
                        )
                        processed += 1
                        continue

                # Check if EnrichmentBuild exists
                existing_build = enrichment_build_repo.find_by_build_id_and_repo(
                    build_id, str(enrichment_repo.id)
                )

                if existing_build and skip_existing:
                    # Already has features, skip
                    skipped += 1
                    enriched_rows.append(
                        {
                            **row,
                            **existing_build.features,
                        }
                    )
                    processed += 1
                    continue

                # Create or get workflow run
                workflow_run = _get_or_create_workflow_run(
                    workflow_repo, enrichment_repo, build_id, commit_sha
                )

                # Create EnrichmentBuild
                enrichment_build = existing_build or EnrichmentBuild(
                    enrichment_repo_id=enrichment_repo.id,
                    dataset_id=enrichment_repo.dataset_id,
                    build_id=build_id,
                    commit_sha=commit_sha or "",
                )

                if not existing_build:
                    enrichment_build = enrichment_build_repo.insert_one(
                        enrichment_build
                    )

                # Run pipeline
                result = pipeline.run(
                    build_sample=enrichment_build,
                    repo=enrichment_repo,
                    workflow_run=workflow_run,
                    features_filter=(
                        set(selected_features) if selected_features else None
                    ),
                )

                if result["status"] == "completed":
                    # Format features for storage (convert lists to strings)
                    from app.pipeline.core.registry import feature_registry

                    formatted_features = feature_registry.format_features_for_storage(
                        result["features"]
                    )

                    # Save features to enrichment build
                    enrichment_build_repo.update_one(
                        str(enrichment_build.id),
                        {
                            "features": formatted_features,
                            "extraction_status": "completed",
                        },
                    )
                    enriched += 1
                    enriched_rows.append(
                        {
                            **row,
                            **formatted_features,
                        }
                    )
                else:
                    failed += 1
                    error_msg = result.get("errors", ["Unknown error"])[0]
                    job_repo.update_progress(
                        job_id,
                        processed + 1,
                        enriched,
                        failed,
                        {"row_index": idx, "error": error_msg},
                    )

                processed += 1

                # Emit progress every 10 rows
                if processed % 10 == 0 or processed == total_rows:
                    publish_progress(
                        job_id,
                        {
                            "type": "progress",
                            "job_id": job_id,
                            "processed_rows": processed,
                            "total_rows": total_rows,
                            "enriched_rows": enriched,
                            "failed_rows": failed,
                            "progress_percent": (processed / total_rows) * 100,
                            "current_repo": repo_name,
                        },
                    )
                    job_repo.update_progress(job_id, processed, enriched, failed)

            except Exception as e:
                logger.error(f"Error processing row {idx}: {e}", exc_info=True)
                failed += 1
                processed += 1
                job_repo.update_progress(
                    job_id,
                    processed,
                    enriched,
                    failed,
                    {"row_index": idx, "error": str(e)},
                )

        # Write enriched CSV
        output_file = _write_enriched_csv(csv_path, enriched_rows, selected_features)

        # Mark job complete
        job_repo.update_one(
            job_id,
            {
                "processed_rows": processed,
                "enriched_rows": enriched,
                "failed_rows": failed,
                "skipped_rows": skipped,
                "repos_auto_imported": list(repos_imported),
            },
        )
        job_repo.mark_completed(job_id, output_file=str(output_file))

        # Emit completion event
        publish_progress(
            job_id,
            {
                "type": "complete",
                "job_id": job_id,
                "status": "completed",
                "total_rows": total_rows,
                "enriched_rows": enriched,
                "failed_rows": failed,
                "output_file": str(output_file),
            },
        )

        return {
            "status": "completed",
            "total_rows": total_rows,
            "enriched_rows": enriched,
            "failed_rows": failed,
            "output_file": str(output_file),
        }

    except Exception as e:
        logger.error(f"Enrichment task failed: {e}", exc_info=True)
        job_repo.mark_failed(job_id, str(e))

        publish_progress(
            job_id,
            {
                "type": "error",
                "job_id": job_id,
                "message": str(e),
            },
        )

        return {
            "status": "failed",
            "error": str(e),
        }


def _auto_import_enrichment_repo(
    enrichment_repo_repo: EnrichmentRepositoryRepository,
    dataset_id: str,
    repo_name: str,
) -> Optional[EnrichmentRepository]:
    """
    Auto-import a repository for dataset enrichment.

    Args:
        enrichment_repo_repo: Enrichment repository repository
        dataset_id: Dataset ID to link the repo to
        repo_name: Full repo name (owner/repo)

    Returns:
        EnrichmentRepository if successful, None otherwise
    """
    try:
        from bson import ObjectId
        from app.entities.enrichment_repository import EnrichmentImportStatus
        from app.ci_providers.models import CIProvider

        # Validate repo name format
        parts = repo_name.split("/")
        if len(parts) != 2:
            logger.warning(f"Invalid repo name format: {repo_name}")
            return None

        # Create enrichment repo linked to dataset
        return enrichment_repo_repo.create_for_dataset(
            dataset_id=dataset_id,
            full_name=repo_name,
            ci_provider=CIProvider.GITHUB_ACTIONS.value,
        )

    except Exception as e:
        logger.error(f"Failed to auto-import enrichment repo {repo_name}: {e}")
        return None


def _get_or_create_workflow_run(
    workflow_repo: WorkflowRunRepository,
    repo: Any,
    build_id: str,
    commit_sha: Optional[str],
) -> Optional[WorkflowRunRaw]:
    """
    Get or create a workflow run record.

    In production, this would fetch from GitHub API.
    For now, create a minimal placeholder.
    """
    try:
        # Try to find existing
        existing = workflow_repo.find_by_build_id(build_id)
        if existing:
            return existing

        # Create minimal placeholder
        from bson import ObjectId

        workflow = WorkflowRunRaw(
            repo_id=ObjectId(str(repo.id)),
            workflow_run_id=int(build_id) if build_id.isdigit() else hash(build_id),
            head_sha=commit_sha or "",
            run_number=0,
            status="completed",
            conclusion="success",
            branch="",
            ci_created_at=datetime.now(timezone.utc),
            ci_updated_at=datetime.now(timezone.utc),
        )

        return workflow_repo.create(workflow)

    except Exception as e:
        logger.warning(f"Failed to get/create workflow run: {e}")
        return None


def _write_enriched_csv(
    original_path: Path,
    enriched_rows: List[Dict[str, Any]],
    feature_columns: List[str],
) -> Path:
    """
    Write enriched data to a new CSV file.

    Args:
        original_path: Path to original CSV
        enriched_rows: Rows with features added
        feature_columns: List of feature column names

    Returns:
        Path to enriched CSV
    """
    # Create output path
    output_dir = original_path.parent / "enriched"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{original_path.stem}_enriched.csv"

    if not enriched_rows:
        # Empty file
        output_path.touch()
        return output_path

    # Get all columns (original + features)
    all_columns = list(enriched_rows[0].keys())

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_columns)
        writer.writeheader()
        writer.writerows(enriched_rows)

    return output_path


@shared_task(
    name="app.tasks.enrichment.run_scheduled_enrichments",
    bind=True,
    queue="data_processing",
)
def run_scheduled_enrichments(self) -> Dict[str, Any]:
    """
    Run scheduled enrichment jobs for datasets with auto-refresh enabled.

    Checks for datasets with enrichment_schedule set and triggers
    enrichment if the last enrichment was before the schedule interval.
    """
    from datetime import timedelta
    from bson import ObjectId

    db = get_database()
    dataset_repo = DatasetRepository(db)
    job_repo = EnrichmentJobRepository(db)

    # Find datasets with schedules
    # For now, we look for datasets that have:
    # 1. enrichment_schedule field set (e.g., "daily", "weekly")
    # 2. Last enrichment older than the schedule interval

    results = {
        "checked": 0,
        "triggered": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        # Query datasets with enrichment schedule
        datasets = list(
            db.datasets.find(
                {
                    "enrichment_schedule": {"$exists": True, "$ne": None},
                    "selected_features": {"$exists": True, "$ne": []},
                }
            )
        )

        for dataset in datasets:
            results["checked"] += 1
            dataset_id = str(dataset["_id"])

            try:
                schedule = dataset.get("enrichment_schedule", "")
                last_enriched = dataset.get("last_enriched_at")

                # Calculate interval
                if schedule == "hourly":
                    interval = timedelta(hours=1)
                elif schedule == "daily":
                    interval = timedelta(days=1)
                elif schedule == "weekly":
                    interval = timedelta(weeks=1)
                else:
                    results["skipped"] += 1
                    continue

                # Check if enrichment is due
                now = datetime.now(timezone.utc)
                if last_enriched:
                    if isinstance(last_enriched, str):
                        last_enriched = datetime.fromisoformat(
                            last_enriched.replace("Z", "+00:00")
                        )
                    if now - last_enriched < interval:
                        results["skipped"] += 1
                        continue

                # Check if there's already a running job
                existing_job = job_repo.find_pending_or_running(dataset_id)
                if existing_job:
                    results["skipped"] += 1
                    continue

                # Create enrichment job
                from app.entities.enrichment_job import EnrichmentJob

                job = EnrichmentJob(
                    dataset_id=ObjectId(dataset_id),
                    user_id=ObjectId(
                        dataset.get("user_id", "000000000000000000000000")
                    ),
                    selected_features=dataset.get("selected_features", []),
                    auto_import_repos=True,
                    skip_existing=True,
                )
                job = job_repo.insert_one(job)

                # Trigger enrichment task
                enrich_dataset_task.delay(
                    job_id=str(job.id),
                    dataset_id=dataset_id,
                    user_id=str(dataset.get("user_id", "")),
                    selected_features=dataset.get("selected_features", []),
                    auto_import_repos=True,
                    skip_existing=True,
                )

                results["triggered"] += 1
                logger.info(f"Triggered scheduled enrichment for dataset {dataset_id}")

            except Exception as e:
                error_msg = f"Dataset {dataset_id}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(f"Scheduled enrichment error: {error_msg}")

    except Exception as e:
        logger.error(f"run_scheduled_enrichments failed: {e}")
        results["errors"].append(str(e))

    logger.info(
        f"Scheduled enrichments: checked={results['checked']}, "
        f"triggered={results['triggered']}, skipped={results['skipped']}"
    )

    return results
