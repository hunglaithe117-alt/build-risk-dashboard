"""
Dataset Processing Tasks.

Celery tasks for Custom Dataset Builder.
Processes dataset extraction jobs with optimized resource usage.
"""

import csv
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.celery_app import celery_app
from app.config import settings
from app.models.entities.build_sample import BuildSample
from app.models.entities.dataset_job import DatasetJobStatus
from app.models.entities.workflow_run import WorkflowRunRaw
from app.pipeline.runner import FeaturePipeline
from app.repositories.dataset_job import DatasetJobRepository
from app.repositories.dataset_sample import DatasetSampleRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.workflow_run import WorkflowRunRepository
from app.tasks.base import PipelineTask

logger = logging.getLogger(__name__)

# Output directory for dataset files
DATASET_OUTPUT_DIR = Path(os.getenv("DATASET_OUTPUT_DIR", "../repo-data/datasets"))
DATASET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def publish_job_update(job_id: str, status: str, progress: int = 0, phase: str = ""):
    """Publish job status update via Redis pub/sub."""
    import json
    import redis

    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.publish(
            "events",
            json.dumps(
                {
                    "type": "DATASET_JOB_UPDATE",
                    "payload": {
                        "job_id": job_id,
                        "status": status,
                        "progress": progress,
                        "phase": phase,
                    },
                }
            ),
        )
    except Exception as e:
        logger.error(f"Failed to publish job update: {e}")


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.dataset.process_dataset_job",
    queue="data_processing",
    soft_time_limit=3600,  # 1 hour soft limit
    time_limit=3900,       # 1.1 hour hard limit
)
def process_dataset_job(self: PipelineTask, job_id: str) -> Dict[str, Any]:
    """
    Process a dataset extraction job.
    
    This task:
    1. Validates the job and repository
    2. Clones repository (if needed)
    3. Collects workflow runs
    4. Extracts features for each build (only required nodes)
    5. Exports results to CSV
    """
    job_repo = DatasetJobRepository(self.db)
    
    # Load job
    job = job_repo.find_by_id(ObjectId(job_id))
    if not job:
        logger.error(f"Dataset job not found: {job_id}")
        return {"status": "error", "message": "Job not found"}
    
    try:
        # Update status to processing
        job_repo.update_status(job_id, DatasetJobStatus.PROCESSING)
        publish_job_update(job_id, "processing", 0, "initializing")
        
        # Extract repo info from URL
        repo_info = parse_github_url(job.repo_url)
        if not repo_info:
            raise ValueError(f"Invalid GitHub URL: {job.repo_url}")
        
        full_name = repo_info["full_name"]
        
        # Phase 1: Find or import repository
        job_repo.update_progress(job_id, 0, 0, "finding_repository")
        publish_job_update(job_id, "processing", 5, "finding_repository")
        
        imported_repo_repo = ImportedRepositoryRepository(self.db)
        repo = imported_repo_repo.find_by_full_name("github", full_name)
        
        if not repo:
            # Need to collect workflow data first
            logger.info(f"Repository not imported, will collect from GitHub: {full_name}")
            repo = import_repository_for_dataset(
                self.db, 
                full_name, 
                str(job.user_id),
                job.max_builds,
            )
            if not repo:
                raise ValueError(f"Failed to import repository: {full_name}")
        
        repo_id = str(repo.id)
        
        # Phase 2: Get workflow runs
        job_repo.update_progress(job_id, 0, 0, "collecting_builds")
        publish_job_update(job_id, "processing", 10, "collecting_builds")
        
        workflow_run_repo = WorkflowRunRepository(self.db)
        workflow_runs = get_workflow_runs_for_job(
            workflow_run_repo, 
            repo_id, 
            job.max_builds,
        )
        
        total_builds = len(workflow_runs)
        if total_builds == 0:
            raise ValueError("No workflow runs found for repository")
        
        job_repo.update_one(job_id, {"total_builds": total_builds})
        logger.info(f"Found {total_builds} workflow runs to process")
        
        # Phase 3: Extract features
        job_repo.update_progress(job_id, 0, 0, "extracting_features")
        publish_job_update(job_id, "processing", 15, "extracting_features")
        
        # Create optimized pipeline with only required nodes
        pipeline = FeaturePipeline(
            db=self.db,
            max_workers=2,  # Conservative for batch processing
            use_definitions=True,
            filter_active_only=True,
        )
        
        # Prepare feature filter
        features_filter = set(job.resolved_features)
        
        # Process each build and collect results using DatasetSample
        dataset_sample_repo = DatasetSampleRepository(self.db)
        processed = 0
        failed = 0
        
        for i, workflow_run in enumerate(workflow_runs):
            try:
                # Create or find dataset sample for this job
                dataset_sample = dataset_sample_repo.find_by_job_and_run_id(
                    job_id, workflow_run.workflow_run_id
                )
                
                if not dataset_sample:
                    # Create new dataset sample
                    sample_data = {
                        "job_id": ObjectId(job_id),
                        "repo_id": ObjectId(repo_id),
                        "workflow_run_id": workflow_run.workflow_run_id,
                        "commit_sha": workflow_run.head_sha,
                        "build_number": workflow_run.run_number,
                        "build_status": workflow_run.conclusion,
                        "build_created_at": workflow_run.created_at,
                        "status": "pending",
                    }
                    dataset_sample = dataset_sample_repo.insert_one(sample_data)
                
                # Create in-memory BuildSample for pipeline (not saved to DB)
                # This is a lightweight object just to pass to the pipeline
                build_sample = BuildSample(
                    _id=ObjectId(),  # Temporary ID (using alias)
                    repo_id=ObjectId(repo_id),
                    workflow_run_id=workflow_run.workflow_run_id,
                    status="pending",
                    tr_build_number=workflow_run.run_number,
                    tr_original_commit=workflow_run.head_sha,
                )
                
                # Run pipeline
                result = pipeline.run(
                    build_sample=build_sample,
                    repo=repo,
                    workflow_run=workflow_run,
                    parallel=True,
                    features_filter=features_filter,
                )
                
                if result["status"] in ["completed", "partial"]:
                    # Save extracted features to dataset sample
                    features_to_save = {}
                    for feature in job.resolved_features:
                        features_to_save[feature] = result["features"].get(feature)
                    
                    dataset_sample_repo.save_features(
                        str(dataset_sample.id),
                        features_to_save,
                    )
                    processed += 1
                else:
                    dataset_sample_repo.update_status(
                        str(dataset_sample.id),
                        "failed",
                        error_message=str(result.get("errors", "Unknown error")),
                    )
                    failed += 1
                    logger.warning(
                        f"Build {workflow_run.workflow_run_id} extraction failed: {result.get('errors')}"
                    )
                
            except Exception as e:
                failed += 1
                logger.error(f"Error processing build {workflow_run.workflow_run_id}: {e}")
                # Update sample status if it exists
                if dataset_sample:
                    dataset_sample_repo.update_status(
                        str(dataset_sample.id),
                        "failed",
                        error_message=str(e),
                    )
            
            # Update progress
            progress_pct = 15 + int((i + 1) / total_builds * 75)  # 15-90%
            job_repo.update_progress(job_id, processed, failed, "extracting_features")
            
            if (i + 1) % 10 == 0:  # Publish every 10 builds
                publish_job_update(job_id, "processing", progress_pct, "extracting_features")
        
        # Phase 4: Export to CSV from DatasetSamples
        job_repo.update_progress(job_id, processed, failed, "exporting_csv")
        publish_job_update(job_id, "processing", 92, "exporting_csv")
        
        # Get all completed samples for this job
        completed_samples = dataset_sample_repo.get_completed_samples(job_id)
        
        if not completed_samples:
            raise ValueError("No successful extractions to export")
        
        # Generate output file
        output_path = DATASET_OUTPUT_DIR / f"{job_id}.csv"
        
        # Build column headers
        columns = []
        if job.include_metadata:
            columns.extend(["commit_sha", "build_number", "build_status", "created_at"])
        columns.extend(sorted(job.resolved_features))
        
        # Build rows from dataset samples
        rows = []
        for sample in completed_samples:
            row = {}
            
            if job.include_metadata:
                row["commit_sha"] = sample.commit_sha
                row["build_number"] = sample.build_number
                row["build_status"] = sample.build_status
                row["created_at"] = sample.build_created_at.isoformat() if sample.build_created_at else ""
            
            # Add features in consistent order
            for feature in sorted(job.resolved_features):
                row[feature] = sample.features.get(feature)
            
            rows.append(row)
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        
        file_size = output_path.stat().st_size
        row_count = len(rows)
        
        # Phase 5: Complete
        job_repo.update_status(
            job_id,
            DatasetJobStatus.COMPLETED,
        )
        job_repo.set_output(job_id, str(output_path), file_size, row_count)
        job_repo.update_progress(job_id, processed, failed, "completed")
        
        publish_job_update(job_id, "completed", 100, "completed")
        
        logger.info(
            f"Dataset job {job_id} completed: {row_count} rows, "
            f"{file_size} bytes, {processed} succeeded, {failed} failed"
        )
        
        return {
            "status": "completed",
            "job_id": job_id,
            "row_count": row_count,
            "file_size": file_size,
            "file_path": str(output_path),
        }
        
    except Exception as e:
        logger.error(f"Dataset job {job_id} failed: {e}", exc_info=True)
        
        job_repo.update_status(
            job_id,
            DatasetJobStatus.FAILED,
            error_message=str(e),
        )
        publish_job_update(job_id, "failed", 0, "failed")
        
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(e),
        }


def parse_github_url(url: str) -> Optional[Dict[str, str]]:
    """Parse GitHub URL to extract owner and repo."""
    import re
    
    patterns = [
        r"github\.com[:/]([^/]+)/([^/\.]+)",  # git@ or https://
        r"^([^/]+)/([^/]+)$",  # owner/repo format
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            owner, repo = match.groups()
            repo = repo.rstrip(".git")
            return {
                "owner": owner,
                "repo": repo,
                "full_name": f"{owner}/{repo}",
            }
    
    return None


def import_repository_for_dataset(
    db,
    full_name: str,
    user_id: str,
    max_builds: Optional[int],
) -> Optional[Any]:
    """
    Import a repository for dataset extraction.
    
    Simplified import that just collects workflow runs.
    """
    from app.services.github.github_client import get_public_github_client
    from app.models.entities.imported_repository import ImportStatus
    from app.repositories.imported_repository import ImportedRepositoryRepository
    from app.repositories.workflow_run import WorkflowRunRepository
    
    repo_repo = ImportedRepositoryRepository(db)
    workflow_run_repo = WorkflowRunRepository(db)
    
    try:
        with get_public_github_client() as gh:
            # Get repo metadata
            repo_data = gh.get_repository(full_name)
            
            # Create imported repo record using dict
            repo_doc = {
                "user_id": ObjectId(user_id),
                "full_name": full_name,
                "github_repo_id": repo_data.get("id"),
                "default_branch": repo_data.get("default_branch", "main"),
                "is_private": bool(repo_data.get("private")),
                "main_lang": repo_data.get("language"),
                "import_status": ImportStatus.IMPORTING.value,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            repo = repo_repo.insert_one(repo_doc)
            repo_id = str(repo.id)
            
            # Collect workflow runs using the repos/{owner}/{repo}/actions/runs endpoint
            per_page = min(max_builds or 100, 100)
            
            # Use the GitHub client's internal method to get workflow runs
            workflow_runs_data = gh._rest_request(
                "GET",
                f"/repos/{full_name}/actions/runs",
                params={"per_page": per_page}
            )
            runs = workflow_runs_data.get("workflow_runs", [])
            
            # Save workflow runs
            count = 0
            for run in runs:
                if max_builds and count >= max_builds:
                    break
                
                workflow_run_doc = {
                    "repo_id": ObjectId(repo_id),
                    "workflow_run_id": run.get("id"),
                    "run_number": run.get("run_number"),
                    "head_sha": run.get("head_sha"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "created_at": datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")) if run.get("created_at") else datetime.now(timezone.utc),
                    "updated_at": datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00")) if run.get("updated_at") else datetime.now(timezone.utc),
                    "raw_payload": run,
                    "log_fetched": False,
                }
                workflow_run_repo.insert_one(workflow_run_doc)
                count += 1
            
            # Update repo status
            repo_repo.update_one(repo_id, {
                "import_status": ImportStatus.IMPORTED.value,
                "total_builds_imported": count,
                "updated_at": datetime.now(timezone.utc),
            })
            
            return repo_repo.find_by_id(repo_id)
            
    except Exception as e:
        logger.error(f"Failed to import repository {full_name}: {e}")
        return None


def get_workflow_runs_for_job(
    workflow_run_repo: WorkflowRunRepository,
    repo_id: str,
    max_builds: Optional[int],
) -> List[WorkflowRunRaw]:
    """Get workflow runs for a dataset job."""
    # Get most recent workflow runs
    query = {"repo_id": ObjectId(repo_id), "conclusion": {"$ne": None}}
    
    cursor = workflow_run_repo.collection.find(query).sort("created_at", -1)
    
    if max_builds:
        cursor = cursor.limit(max_builds)
    
    return [WorkflowRunRaw(**doc) for doc in cursor]
