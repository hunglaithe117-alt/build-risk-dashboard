"""
Enrichment Task - Background processing for dataset enrichment.

This task processes CSV rows to:
1. Auto-import missing repositories
2. Create BuildSample records
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
from app.entities.build_sample import BuildSample
from app.entities.workflow_run import WorkflowRunRaw
from app.repositories.enrichment_job import EnrichmentJobRepository
from app.repositories.build_sample import BuildSampleRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
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
        client.publish(
            f"{REDIS_CHANNEL_PREFIX}{job_id}",
            json.dumps(event)
        )
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
    repo_repo = ImportedRepositoryRepository(db)
    build_repo = BuildSampleRepository(db)
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
                commit_sha = row.get(commit_sha_col, "").strip() if commit_sha_col else None

                if not repo_name or not build_id:
                    failed += 1
                    job_repo.update_progress(
                        job_id, processed + 1, enriched, failed,
                        {"row_index": idx, "error": "Missing repo_name or build_id"}
                    )
                    processed += 1
                    continue

                # Check if repo exists
                repo = repo_repo.find_by_full_name(repo_name)

                if not repo:
                    if auto_import_repos:
                        # Auto-import repo
                        repo = _auto_import_repo(repo_repo, repo_name, user_id)
                        if repo:
                            repos_imported.add(repo_name)
                            job_repo.add_auto_imported_repo(job_id, repo_name)
                    
                    if not repo:
                        failed += 1
                        job_repo.update_progress(
                            job_id, processed + 1, enriched, failed,
                            {"row_index": idx, "error": f"Repository not found: {repo_name}"}
                        )
                        processed += 1
                        continue

                # Check if BuildSample exists
                existing_build = build_repo.find_by_build_id_and_repo(
                    build_id, str(repo.id)
                )

                if existing_build and skip_existing:
                    # Already has features, skip
                    skipped += 1
                    enriched_rows.append({
                        **row,
                        **existing_build.features,
                    })
                    processed += 1
                    continue

                # Create or get workflow run
                workflow_run = _get_or_create_workflow_run(
                    workflow_repo, repo, build_id, commit_sha
                )

                # Create BuildSample
                build_sample = existing_build or BuildSample(
                    repository_id=str(repo.id),
                    workflow_run_id=str(workflow_run.id) if workflow_run else None,
                    build_id=build_id,
                    commit_sha=commit_sha or "",
                )

                if not existing_build:
                    build_sample = build_repo.create(build_sample)

                # Run pipeline
                result = pipeline.run(
                    build_sample=build_sample,
                    repo=repo,
                    workflow_run=workflow_run,
                    features_filter=set(selected_features) if selected_features else None,
                )

                if result["status"] == "completed":
                    # Save features to build sample
                    build_repo.update_features(
                        str(build_sample.id),
                        result["features"]
                    )
                    enriched += 1
                    enriched_rows.append({
                        **row,
                        **result["features"],
                    })
                else:
                    failed += 1
                    error_msg = result.get("errors", ["Unknown error"])[0]
                    job_repo.update_progress(
                        job_id, processed + 1, enriched, failed,
                        {"row_index": idx, "error": error_msg}
                    )

                processed += 1

                # Emit progress every 10 rows
                if processed % 10 == 0 or processed == total_rows:
                    publish_progress(job_id, {
                        "type": "progress",
                        "job_id": job_id,
                        "processed_rows": processed,
                        "total_rows": total_rows,
                        "enriched_rows": enriched,
                        "failed_rows": failed,
                        "progress_percent": (processed / total_rows) * 100,
                        "current_repo": repo_name,
                    })
                    job_repo.update_progress(job_id, processed, enriched, failed)

            except Exception as e:
                logger.error(f"Error processing row {idx}: {e}", exc_info=True)
                failed += 1
                processed += 1
                job_repo.update_progress(
                    job_id, processed, enriched, failed,
                    {"row_index": idx, "error": str(e)}
                )

        # Write enriched CSV
        output_file = _write_enriched_csv(csv_path, enriched_rows, selected_features)

        # Mark job complete
        job_repo.update_one(job_id, {
            "processed_rows": processed,
            "enriched_rows": enriched,
            "failed_rows": failed,
            "skipped_rows": skipped,
            "repos_auto_imported": list(repos_imported),
        })
        job_repo.mark_completed(job_id, output_file=str(output_file))

        # Emit completion event
        publish_progress(job_id, {
            "type": "complete",
            "job_id": job_id,
            "status": "completed",
            "total_rows": total_rows,
            "enriched_rows": enriched,
            "failed_rows": failed,
            "output_file": str(output_file),
        })

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
        
        publish_progress(job_id, {
            "type": "error",
            "job_id": job_id,
            "message": str(e),
        })

        return {
            "status": "failed",
            "error": str(e),
        }


def _auto_import_repo(
    repo_repo: ImportedRepositoryRepository,
    repo_name: str,
    user_id: str,
) -> Optional[Any]:
    """
    Auto-import a repository from GitHub.

    Args:
        repo_repo: Repository repository
        repo_name: Full repo name (owner/repo)
        user_id: User ID

    Returns:
        ImportedRepository if successful, None otherwise
    """
    try:
        from app.entities.imported_repository import ImportedRepository, ImportStatus

        # Parse owner/repo
        parts = repo_name.split("/")
        if len(parts) != 2:
            logger.warning(f"Invalid repo name format: {repo_name}")
            return None

        owner, name = parts

        # Create basic repo record (GitHub data fetch happens async)
        repo = ImportedRepository(
            full_name=repo_name,
            owner=owner,
            name=name,
            import_status=ImportStatus.PENDING,
            imported_by=user_id,
        )

        return repo_repo.create(repo)

    except Exception as e:
        logger.error(f"Failed to auto-import repo {repo_name}: {e}")
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
        workflow = WorkflowRunRaw(
            repository_id=str(repo.id),
            run_id=int(build_id) if build_id.isdigit() else hash(build_id),
            name="Unknown",
            head_sha=commit_sha or "",
            status="completed",
            conclusion="success",
            created_at=datetime.now(timezone.utc),
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
