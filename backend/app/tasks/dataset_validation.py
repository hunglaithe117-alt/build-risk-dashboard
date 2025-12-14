"""
Dataset Validation Tasks - Chain+Group pattern for parallel validation.

Flow:
1. start_validation - Orchestrator: Parse CSV, dispatch per-repo tasks
2. validate_repo_builds - Validate all builds for a single repository
3. finalize_validation - Aggregate results, update dataset status
"""

import logging
from typing import Any, Dict, List

import pandas as pd
from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.config import settings
from app.core.redis import get_redis
from app.database.mongo import get_database
from app.entities import (
    DatasetBuild,
    DatasetBuildStatus,
    ValidationStats,
)
from backend.app.entities.raw_build_run import RawWorkflowRun
from app.ci_providers.factory import get_ci_provider
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from backend.app.repositories.raw_build_run import RawWorkflowRunRepository
from app.utils.datetime import utc_now
from backend.app.ci_providers.models import CIProvider
from backend.app.entities.enums import DatasetRepoValidationStatus

logger = logging.getLogger(__name__)


def parse_csv_with_pandas(
    file_path: str,
    build_id_column: str,
    repo_name_column: str,
) -> pd.DataFrame:
    """Parse CSV file and extract build_id and repo_name columns."""
    df = pd.read_csv(file_path, dtype=str)

    if build_id_column not in df.columns or repo_name_column not in df.columns:
        raise ValueError(
            f"Required columns not found: {build_id_column}, {repo_name_column}"
        )

    df = df[[build_id_column, repo_name_column]].dropna()
    df = df.rename(
        columns={
            build_id_column: "build_id",
            repo_name_column: "repo_name",
        }
    )
    df["build_id"] = df["build_id"].str.strip()
    df["repo_name"] = df["repo_name"].str.strip()
    df = df[(df["build_id"] != "") & (df["repo_name"] != "")]

    return df


# Task 1: Orchestrator
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.start_validation",
    queue="validation",
)
def start_validation(self, dataset_id: str) -> Dict[str, Any]:
    """
    Orchestrator: Parse CSV and dispatch per-repo validation tasks.

    Flow: start_validation -> chord(group([validate_repo_builds x N]), finalize_validation)
    """
    db = get_database()
    dataset_repo = DatasetRepository(db)
    enrichment_repo_repo = DatasetRepoConfigRepository(db)

    try:
        dataset_doc = dataset_repo.find_by_id(dataset_id)
        if not dataset_doc:
            raise ValueError(f"Dataset {dataset_id} not found")

        dataset = dataset_doc

        # Mark as started
        dataset_repo.update_one(
            dataset_id,
            {
                "validation_status": "validating",
                "validation_started_at": utc_now(),
                "validation_task_id": self.request.id,
                "validation_progress": 0,
                "validation_error": None,
            },
        )

        # Get validated repos from Step 2
        saved_repos_list = enrichment_repo_repo.find_many(
            {
                "dataset_id": ObjectId(dataset_id),
                "validation_status": DatasetRepoValidationStatus.VALID,
            }
        )
        saved_repos = {repo.normalized_full_name: repo for repo in saved_repos_list}

        if not saved_repos:
            raise ValueError(
                "No validated repositories found. Please complete Step 2 first."
            )

        # Parse CSV
        file_path = dataset.file_path
        build_id_col = dataset.mapped_fields.build_id
        repo_name_col = dataset.mapped_fields.repo_name

        if not build_id_col or not repo_name_col:
            raise ValueError("Dataset mapping not configured")

        df = parse_csv_with_pandas(file_path, build_id_col, repo_name_col)

        valid_repo_names = set(saved_repos.keys())
        df_filtered = df[df["repo_name"].isin(valid_repo_names)]

        # Group builds by repo
        repo_builds: Dict[str, List[str]] = {}
        for _, row in df_filtered.iterrows():
            repo = row["repo_name"]
            build_id = row["build_id"]
            if repo not in repo_builds:
                repo_builds[repo] = []
            repo_builds[repo].append(build_id)

        # Deduplicate
        repo_builds = {repo: list(set(builds)) for repo, builds in repo_builds.items()}

        total_repos = len(repo_builds)
        total_builds = sum(len(builds) for builds in repo_builds.values())

        skipped_repos = set(df["repo_name"].unique()) - valid_repo_names

        # Initial stats
        initial_stats = {
            "repos_total": total_repos,
            "repos_not_found": len(skipped_repos),
            "builds_total": total_builds,
            "repos_valid": 0,
            "builds_found": 0,
            "builds_not_found": 0,
        }

        dataset_repo.update_one(
            dataset_id,
            {"validation_stats": initial_stats},
        )

        if total_repos == 0:
            dataset_repo.update_one(
                dataset_id,
                {
                    "validation_status": "completed",
                    "validation_completed_at": utc_now(),
                    "validation_progress": 100,
                },
            )
            return {"status": "completed", "message": "No repos to validate"}

        # Create tasks for each repo
        repo_tasks = []
        for repo_name, build_ids in repo_builds.items():
            repo_doc = saved_repos[repo_name]
            repo_tasks.append(
                validate_repo_builds.s(
                    dataset_id=dataset_id,
                    repo_id=str(repo_doc.id),
                    repo_name=repo_name,
                    build_ids=build_ids,
                    ci_provider=repo_doc.ci_provider,
                )
            )

        # Use chord to run all repo validations in parallel,
        # then finalize when all complete
        workflow = chord(group(repo_tasks))(
            finalize_validation.s(dataset_id=dataset_id)
        )

        logger.info(
            f"Dispatched validation for {total_repos} repos, {total_builds} builds"
        )

        return {
            "status": "dispatched",
            "repos": total_repos,
            "builds": total_builds,
        }

    except Exception as e:
        logger.exception(f"Dataset validation start failed: {e}")
        dataset_repo.update_one(
            dataset_id,
            {
                "validation_status": "failed",
                "validation_completed_at": utc_now(),
                "validation_error": str(e),
            },
        )
        raise


# Task 2: Per-repo validation
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.validate_repo_builds",
    queue="validation",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": settings.VALIDATION_MAX_RETRIES},
    retry_backoff=True,
    retry_backoff_max=600,
)
def validate_repo_builds(
    self,
    dataset_id: str,
    repo_id: str,
    repo_name: str,
    build_ids: List[str],
    ci_provider: str,
) -> Dict[str, Any]:
    """
    Validate all builds for a single repository.

    Returns stats for this repo to be aggregated by finalize_validation.
    """
    import asyncio

    async def _do_validate():
        db = get_database()
        redis = get_redis()
        dataset_build_repo = DatasetBuildRepository(db)
        enrichment_repo_repo = DatasetRepoConfigRepository(db)
        workflow_run_repo = RawWorkflowRunRepository(db)

        # Check for cancellation
        cancelled = redis.get(f"dataset_validation:{dataset_id}:cancelled")
        if cancelled:
            return {
                "repo_name": repo_name,
                "status": "cancelled",
                "builds_found": 0,
                "builds_not_found": 0,
            }

        ci = get_ci_provider(CIProvider(ci_provider), db=db)

        # Update repo with total builds count
        enrichment_repo_repo.update_one(repo_id, {"builds_total": len(build_ids)})

        builds_found = 0
        builds_not_found = 0

        for build_id in build_ids:
            # Check for cancellation periodically
            cancelled = redis.get(f"dataset_validation:{dataset_id}:cancelled")
            if cancelled:
                break

            # Check if build already validated
            existing_build = dataset_build_repo.find_existing(
                dataset_id, build_id, repo_id
            )

            if existing_build and existing_build.status in [
                "found",
                "not_found",
            ]:
                if existing_build.status == "found":
                    builds_found += 1
                else:
                    builds_not_found += 1
                continue

            dataset_build = DatasetBuild(
                _id=None,
                dataset_id=ObjectId(dataset_id),
                build_id_from_csv=build_id,
                repo_name_from_csv=repo_name,
                repo_id=ObjectId(repo_id),
            )

            try:
                workflow_data = await ci.get_workflow_run(repo_name, int(build_id))

                if workflow_data and ci.is_run_completed(workflow_data):
                    workflow_run = RawWorkflowRun(
                        _id=None,
                        raw_repo_id=ObjectId(repo_id),
                        workflow_run_id=int(build_id),
                        ci_provider=ci_provider,
                        head_sha=workflow_data.get("head_sha", ""),
                        run_number=workflow_data.get("run_number", 0),
                        status=workflow_data.get("status", "unknown"),
                        conclusion=workflow_data.get("conclusion", ""),
                        branch=workflow_data.get("head_branch", ""),
                        ci_created_at=workflow_data.get("created_at") or utc_now(),
                        ci_updated_at=workflow_data.get("updated_at") or utc_now(),
                        raw_payload=workflow_data,
                    )
                    workflow_run = workflow_run_repo.insert_one(workflow_run)
                    dataset_build.status = DatasetBuildStatus.FOUND
                    dataset_build.workflow_run_id = workflow_run.id
                    dataset_build.validated_at = utc_now()
                    builds_found += 1
                else:
                    dataset_build.status = DatasetBuildStatus.NOT_FOUND
                    dataset_build.validation_error = (
                        "Build found but not completed"
                        if workflow_data
                        else "Build not found"
                    )
                    dataset_build.validated_at = utc_now()
                    builds_not_found += 1

            except Exception as e:
                logger.error(
                    f"Build validation error for repo={repo_name}, "
                    f"build_id={build_id}: {e}",
                    exc_info=True,
                )
                dataset_build.status = DatasetBuildStatus.ERROR
                dataset_build.validation_error = str(e)
                dataset_build.validated_at = utc_now()
                builds_not_found += 1

            dataset_build_repo.insert_one(dataset_build)

        # Update repo build statistics
        enrichment_repo_repo.update_one(
            repo_id,
            {
                "builds_found": builds_found,
                "builds_not_found": builds_not_found,
            },
        )

        return {
            "repo_name": repo_name,
            "repo_id": repo_id,
            "status": "completed",
            "builds_found": builds_found,
            "builds_not_found": builds_not_found,
            "builds_total": len(build_ids),
        }

    return asyncio.run(_do_validate())


# Task 3: Finalize
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.finalize_validation",
    queue="validation",
)
def finalize_validation(
    self,
    repo_results: List[Dict[str, Any]],
    dataset_id: str,
) -> Dict[str, Any]:
    """
    Aggregate results from all repo validations and update dataset status.
    """
    db = get_database()
    dataset_repo = DatasetRepository(db)

    # Aggregate stats
    total_repos = len(repo_results)
    total_builds_found = 0
    total_builds_not_found = 0
    total_builds = 0
    cancelled = False

    for result in repo_results:
        if result.get("status") == "cancelled":
            cancelled = True
        total_builds_found += result.get("builds_found", 0)
        total_builds_not_found += result.get("builds_not_found", 0)
        total_builds += result.get("builds_total", 0)

    stats = ValidationStats(
        repos_total=total_repos,
        repos_valid=total_repos,
        repos_not_found=0,
        builds_total=total_builds,
        builds_found=total_builds_found,
        builds_not_found=total_builds_not_found,
    )

    build_coverage = (
        round((total_builds_found / total_builds) * 100, 2) if total_builds > 0 else 0.0
    )

    final_status = "cancelled" if cancelled else "completed"

    dataset_repo.update_one(
        dataset_id,
        {
            "validation_status": final_status,
            "validation_completed_at": utc_now(),
            "validation_progress": 100,
            "validation_stats": stats.model_dump(),
            "stats.build_coverage": build_coverage,
        },
    )

    logger.info(
        f"Dataset validation {final_status}: {dataset_id}, "
        f"{total_builds_found}/{total_builds} builds found"
    )

    return {
        "status": final_status,
        "stats": stats.model_dump(),
        "build_coverage": build_coverage,
    }


# Legacy function for status updates (used by service)
def _update_status(db, dataset_id: str, status: str):
    db.datasets.update_one(
        {"_id": ObjectId(dataset_id)},
        {
            "$set": {
                "validation_status": status,
                "validation_completed_at": utc_now(),
            }
        },
    )
