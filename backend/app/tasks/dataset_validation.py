"""
Dataset Validation Tasks - Chain+Group pattern for parallel validation.

Flow:
1. start_validation - Orchestrator: Parse CSV, dispatch per-repo tasks
2. validate_repo_builds - Validate all builds for a single repository
3. finalize_validation - Aggregate results, update dataset status
"""

from app.entities.dataset import DatasetValidationStatus
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
from app.ci_providers.factory import get_ci_provider
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_repo_config import DatasetRepoConfigRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.utils.datetime import utc_now
from app.ci_providers.models import CIProvider
from app.entities.enums import DatasetRepoValidationStatus

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


def extract_unique_repos(
    file_path: str,
    repo_name_column: str,
) -> tuple[List[str], List[str]]:
    """Extract unique valid and invalid format repos from CSV."""
    df = pd.read_csv(file_path, dtype=str)

    if repo_name_column not in df.columns:
        return [], []

    valid_repos = set()
    invalid_repos = set()

    for repo_name in df[repo_name_column].dropna().unique():
        repo_name = str(repo_name).strip()
        if not repo_name:
            continue
        if "/" in repo_name and len(repo_name.split("/")) == 2:
            owner, name = repo_name.split("/")
            if owner and name:
                valid_repos.add(repo_name)
            else:
                invalid_repos.add(repo_name)
        else:
            invalid_repos.add(repo_name)

    return list(valid_repos), list(invalid_repos)


# REPO VALIDATION TASK (During Upload - Before Step 2)
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.validate_repos_task",
    queue="validation",
    soft_time_limit=300,  # 5 min
    time_limit=360,
)
def validate_repos_task(self, dataset_id: str) -> Dict[str, Any]:
    """
    Validate repositories discovered in CSV during upload.

    Creates RawRepository and DatasetRepoConfig for each valid repo.
    Called immediately after CSV upload, before Step 2.
    """
    from app.entities.dataset import RepoValidationStatus
    from app.repositories.raw_repository import RawRepositoryRepository
    from app.services.github.github_client import get_public_github_client

    db = get_database()
    dataset_repo = DatasetRepository(db)
    repo_config_repo = DatasetRepoConfigRepository(db)
    raw_repo_repo = RawRepositoryRepository(db)

    try:
        dataset = dataset_repo.find_by_id(dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        # Mark as validating
        dataset_repo.update_one(
            dataset_id,
            {
                "repo_validation_status": RepoValidationStatus.VALIDATING,
                "repo_validation_task_id": self.request.id,
                "repo_validation_error": None,
            },
        )

        # Extract repos from CSV
        file_path = dataset.file_path
        repo_name_col = dataset.mapped_fields.repo_name

        if not repo_name_col:
            raise ValueError("repo_name column not mapped")

        valid_names, invalid_names = extract_unique_repos(file_path, repo_name_col)

        logger.info(
            f"Found {len(valid_names)} valid, {len(invalid_names)} invalid repos in dataset {dataset_id}"
        )

        # Validate and create repos
        validated_raw_repo_ids = []
        repos_valid = 0
        repos_not_found = 0

        with get_public_github_client() as gh:
            for full_name in valid_names:
                try:
                    repo_data = gh.get_repository(full_name)

                    is_private = bool(repo_data.get("private"))
                    if is_private:
                        logger.info(f"Repo {full_name} is private, skipping validation")
                        repos_not_found += 1

                        repo_config_repo.upsert_repo(
                            dataset_id=dataset_id,
                            full_name=full_name,
                            ci_provider=CIProvider.GITHUB_ACTIONS,
                            source_languages=[],
                            test_frameworks=[],
                            validation_status=DatasetRepoValidationStatus.NOT_FOUND,
                            raw_repo_id=None,
                            default_branch=None,
                            validation_error="Repo is private",
                        )
                        continue

                    raw_repo = raw_repo_repo.upsert_by_full_name(
                        full_name=full_name,
                        github_repo_id=repo_data.get("id"),
                        default_branch=repo_data.get("default_branch", "main"),
                        is_private=is_private,
                        main_lang=repo_data.get("language"),
                        github_metadata=repo_data,
                    )

                    validated_raw_repo_ids.append(raw_repo.id)

                    repo_config_repo.upsert_repo(
                        dataset_id=dataset_id,
                        full_name=full_name,
                        ci_provider=CIProvider.GITHUB_ACTIONS,
                        source_languages=[],
                        test_frameworks=[],
                        validation_status=DatasetRepoValidationStatus.VALID,
                        raw_repo_id=raw_repo.id,
                        default_branch=repo_data.get("default_branch", "main"),
                    )
                    repos_valid += 1

                except Exception as e:
                    error_msg = str(e)
                    is_not_found = (
                        "404" in error_msg or "not found" in error_msg.lower()
                    )
                    logger.warning(f"Failed to validate repo {full_name}: {error_msg}")

                    # Create DatasetRepoConfig with error status
                    repo_config_repo.upsert_repo(
                        dataset_id=dataset_id,
                        full_name=full_name,
                        ci_provider=CIProvider.GITHUB_ACTIONS,
                        source_languages=[],
                        test_frameworks=[],
                        validation_status=(
                            DatasetRepoValidationStatus.NOT_FOUND
                            if is_not_found
                            else DatasetRepoValidationStatus.ERROR
                        ),
                        raw_repo_id=None,
                        default_branch=None,
                        validation_error=error_msg,
                    )
                    repos_not_found += 1

        # Handle invalid format repos
        for invalid_name in invalid_names:
            repo_config_repo.upsert_repo(
                dataset_id=dataset_id,
                full_name=invalid_name,
                ci_provider=CIProvider.GITHUB_ACTIONS,
                source_languages=[],
                test_frameworks=[],
                validation_status=DatasetRepoValidationStatus.ERROR,
                raw_repo_id=None,
                default_branch="main",
                validation_error="Invalid format (expected owner/repo)",
            )

        # Update dataset with results
        dataset_repo.update_one(
            dataset_id,
            {
                "repo_validation_status": RepoValidationStatus.COMPLETED,
                "validated_raw_repo_ids": validated_raw_repo_ids,
                "validation_stats.repos_total": len(valid_names) + len(invalid_names),
                "validation_stats.repos_valid": repos_valid,
                "validation_stats.repos_not_found": repos_not_found,
                "validation_stats.repos_invalid": len(invalid_names),
            },
        )

        logger.info(
            f"Repo validation completed for dataset {dataset_id}: "
            f"{repos_valid} valid, {repos_not_found} not found, {len(invalid_names)} invalid"
        )

        return {
            "status": "completed",
            "repos_valid": repos_valid,
            "repos_not_found": repos_not_found,
            "repos_invalid": len(invalid_names),
        }

    except Exception as e:
        logger.exception(f"Repo validation failed for dataset {dataset_id}: {e}")
        dataset_repo.update_one(
            dataset_id,
            {
                "repo_validation_status": RepoValidationStatus.FAILED,
                "repo_validation_error": str(e),
            },
        )
        raise


# Task 1: Orchestrator
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.start_validation",
    queue="validation",
    soft_time_limit=300,  # 5 min
    time_limit=360,
)
def start_validation(self, dataset_id: str) -> Dict[str, Any]:
    """
    Orchestrator: Parse CSV and dispatch per-repo validation tasks.

    Flow: start_validation -> chord(group([validate_repo_builds x N]), finalize_validation)
    """
    db = get_database()
    dataset_repo = DatasetRepository(db)
    repo_config_repo = DatasetRepoConfigRepository(db)

    try:
        dataset_doc = dataset_repo.find_by_id(dataset_id)
        if not dataset_doc:
            raise ValueError(f"Dataset {dataset_id} not found")

        dataset = dataset_doc

        # Mark as started
        dataset_repo.update_one(
            dataset_id,
            {
                "validation_status": DatasetValidationStatus.VALIDATING,
                "validation_started_at": utc_now(),
                "validation_task_id": self.request.id,
                "validation_progress": 0,
                "validation_error": None,
            },
        )

        # Get validated repos from Step 2
        saved_repos_list = repo_config_repo.find_many(
            {
                "dataset_id": ObjectId(dataset_id),
                "validation_status": DatasetRepoValidationStatus.VALID,
            }
        )
        saved_repos = {repo.full_name: repo for repo in saved_repos_list}

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
                    "validation_status": DatasetValidationStatus.COMPLETED,
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
                    repo_config_id=str(repo_doc.id),
                    raw_repo_id=str(repo_doc.raw_repo_id),
                    repo_name=repo_name,
                    build_ids=build_ids,
                    ci_provider=repo_doc.ci_provider,
                )
            )

        # Use chord to run all repo validations in parallel,
        # then finalize when all complete
        chord(group(repo_tasks))(finalize_validation.s(dataset_id=dataset_id))

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
                "validation_status": DatasetValidationStatus.FAILED,
                "validation_completed_at": utc_now(),
                "validation_error": str(e),
            },
        )
        raise


# Task 2: Per-repo validation orchestrator
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.validate_repo_builds",
    queue="validation",
    soft_time_limit=300,  # 5 min (just dispatches chunks)
    time_limit=360,
)
def validate_repo_builds(
    self,
    dataset_id: str,
    repo_config_id: str,
    raw_repo_id: str,
    repo_name: str,
    build_ids: List[str],
    ci_provider: str,
) -> Dict[str, Any]:
    """
    Orchestrator: Dispatch build validation in chunks.

    Each chunk runs as a separate task for better fault tolerance.
    """
    redis = get_redis()

    # Check for cancellation
    if redis.get(f"dataset_validation:{dataset_id}:cancelled"):
        return {
            "repo_name": repo_name,
            "status": "cancelled",
            "builds_found": 0,
            "builds_not_found": 0,
        }

    db = get_database()
    repo_config_repo = DatasetRepoConfigRepository(db)

    # Update repo with total builds count
    repo_config_repo.update_one(repo_config_id, {"builds_total": len(build_ids)})

    # Initialize Redis state for this repo's validation
    session_key = f"validate_repo:{dataset_id}:{repo_config_id}"
    redis.delete(f"{session_key}:found")
    redis.delete(f"{session_key}:not_found")
    redis.set(f"{session_key}:found", 0, ex=3600)
    redis.set(f"{session_key}:not_found", 0, ex=3600)

    # Dispatch chunks
    chunk_size = getattr(settings, "VALIDATION_BATCH_SIZE", 50)
    chunks_dispatched = 0

    for i in range(0, len(build_ids), chunk_size):
        chunk = build_ids[i : i + chunk_size]
        validate_builds_chunk.delay(
            dataset_id=dataset_id,
            repo_config_id=repo_config_id,
            raw_repo_id=raw_repo_id,
            repo_name=repo_name,
            build_ids=chunk,
            ci_provider=ci_provider,
            chunk_index=i // chunk_size,
            total_chunks=(len(build_ids) + chunk_size - 1) // chunk_size,
        )
        chunks_dispatched += 1

    logger.info(
        f"Dispatched {chunks_dispatched} validation chunks for repo {repo_name}"
    )

    return {
        "repo_name": repo_name,
        "repo_config_id": repo_config_id,
        "status": "dispatched",
        "chunks_dispatched": chunks_dispatched,
        "builds_total": len(build_ids),
    }


# Task 2b: Per-chunk validation worker
@celery_app.task(
    bind=True,
    name="app.tasks.dataset_validation.validate_builds_chunk",
    queue="validation",
    soft_time_limit=300,  # 5 min per chunk
    time_limit=360,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 30},
    retry_backoff=True,
)
def validate_builds_chunk(
    self,
    dataset_id: str,
    repo_config_id: str,
    raw_repo_id: str,
    repo_name: str,
    build_ids: List[str],
    ci_provider: str,
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> Dict[str, Any]:
    """
    Worker: Validate a chunk of builds for a repository.

    Uses Redis to aggregate results across chunks.
    """
    import asyncio

    async def _do_validate():
        db = get_database()
        redis = get_redis()
        dataset_build_repo = DatasetBuildRepository(db)
        repo_config_repo = DatasetRepoConfigRepository(db)
        build_run_repo = RawBuildRunRepository(db)

        # Check for cancellation
        if redis.get(f"dataset_validation:{dataset_id}:cancelled"):
            return {
                "chunk_index": chunk_index,
                "status": "cancelled",
                "builds_found": 0,
                "builds_not_found": 0,
            }

        ci = get_ci_provider(CIProvider(ci_provider), db=db)

        rate_limit = getattr(settings, "API_RATE_LIMIT_PER_SECOND", 5.0)
        min_interval = 1.0 / rate_limit
        session_key = f"validate_repo:{dataset_id}:{repo_config_id}"

        builds_found = 0
        builds_not_found = 0

        for build_id in build_ids:
            # Check for cancellation
            if redis.get(f"dataset_validation:{dataset_id}:cancelled"):
                break

            # Check if build already validated (idempotency)
            existing_build = dataset_build_repo.find_existing(
                dataset_id, build_id, raw_repo_id
            )

            if existing_build and existing_build.status in ["found", "not_found"]:
                if existing_build.status == "found":
                    builds_found += 1
                else:
                    builds_not_found += 1
                continue

            dataset_build = DatasetBuild(
                _id=None,
                dataset_id=ObjectId(dataset_id),
                build_id_from_csv=build_id,
                full_name=repo_name,
                raw_repo_id=ObjectId(raw_repo_id),
            )

            try:
                await asyncio.sleep(min_interval)
                workflow_data = await ci.get_workflow_run(repo_name, int(build_id))

                if workflow_data and ci.is_run_completed(workflow_data):
                    build_run = build_run_repo.upsert_by_business_key(
                        raw_repo_id=ObjectId(raw_repo_id),
                        build_id=str(build_id),
                        provider=ci_provider,
                        build_number=workflow_data.get("run_number"),
                        repo_name=repo_name,
                        branch=workflow_data.get("head_branch", ""),
                        commit_sha=workflow_data.get("head_sha", ""),
                        commit_message=None,
                        commit_author=None,
                        status=workflow_data.get("status", "unknown"),
                        conclusion=workflow_data.get("conclusion", ""),
                        created_at=workflow_data.get("created_at") or utc_now(),
                        started_at=None,
                        completed_at=workflow_data.get("updated_at") or utc_now(),
                        duration_seconds=None,
                        web_url=workflow_data.get("html_url"),
                        logs_url=None,
                        logs_available=False,
                        logs_path=None,
                        raw_data=workflow_data,
                        is_bot_commit=workflow_data.get("is_bot", False),
                    )

                    dataset_build.status = DatasetBuildStatus.FOUND
                    dataset_build.workflow_run_id = build_run.id
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
                    f"Build validation error for repo={repo_name}, build_id={build_id}: {e}",
                    exc_info=True,
                )
                dataset_build.status = DatasetBuildStatus.ERROR
                dataset_build.validation_error = str(e)
                dataset_build.validated_at = utc_now()
                builds_not_found += 1

            dataset_build_repo.create(dataset_build)

        # Update Redis counters (for aggregation across chunks)
        redis.incrby(f"{session_key}:found", builds_found)
        redis.incrby(f"{session_key}:not_found", builds_not_found)

        # Update repo stats from Redis
        total_found = int(redis.get(f"{session_key}:found") or 0)
        total_not_found = int(redis.get(f"{session_key}:not_found") or 0)

        repo_config_repo.update_one(
            repo_config_id,
            {
                "builds_found": total_found,
                "builds_not_found": total_not_found,
            },
        )

        return {
            "chunk_index": chunk_index,
            "repo_name": repo_name,
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
    soft_time_limit=120,  # 2 min
    time_limit=180,
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
            "setup_step": 3,  # Mark validation complete
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
