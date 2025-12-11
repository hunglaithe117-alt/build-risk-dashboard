import logging
import os
from datetime import datetime
from typing import Dict, Set

import pandas as pd
from bson import ObjectId

from app.celery_app import celery_app
from app.entities import (
    DatasetProject,
    DatasetBuild,
    DatasetBuildStatus,
    ValidationStats,
)
from app.entities.workflow_run import WorkflowRunRaw
from app.ci_providers.factory import get_ci_provider
from app.database.mongo import get_database
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def parse_csv_with_pandas(
    file_path: str,
    build_id_column: str,
    repo_name_column: str,
) -> pd.DataFrame:
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


@celery_app.task(bind=True, name="app.tasks.dataset_validation.validate_dataset_task")
def validate_dataset_task(self, dataset_id: str):
    import asyncio

    async def _do_validate():
        db = get_database()
        redis = get_redis()

        try:
            dataset_doc = db.datasets.find_one({"_id": ObjectId(dataset_id)})
            if not dataset_doc:
                raise ValueError(f"Dataset {dataset_id} not found")

            dataset = DatasetProject(**dataset_doc)

            db.datasets.update_one(
                {"_id": ObjectId(dataset_id)},
                {
                    "$set": {
                        "validation_status": "validating",
                        "validation_started_at": datetime.utcnow(),
                        "validation_task_id": self.request.id,
                        "validation_progress": 0,
                        "validation_error": None,
                    }
                },
            )

            saved_repos_cursor = db.enrichment_repositories.find(
                {
                    "dataset_id": ObjectId(dataset_id),
                    "validation_status": "valid",
                }
            )
            saved_repos = {doc["full_name"]: doc for doc in saved_repos_cursor}

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

            repo_builds: Dict[str, Set[str]] = {}
            for _, row in df_filtered.iterrows():
                repo = row["repo_name"]
                build_id = row["build_id"]
                if repo not in repo_builds:
                    repo_builds[repo] = set()
                repo_builds[repo].add(build_id)

            total_repos = len(repo_builds)
            total_builds = sum(len(builds) for builds in repo_builds.values())

            skipped_repos = set(df["repo_name"].unique()) - valid_repo_names

            stats = ValidationStats(
                repos_total=total_repos,
                repos_not_found=len(skipped_repos),
                builds_total=total_builds,
            )

            repos_processed = 0
            builds_processed = 0

            for repo_name, builds in repo_builds.items():
                cancelled = redis.get(f"dataset_validation:{dataset_id}:cancelled")
                if cancelled:
                    _update_status(db, dataset_id, "cancelled")
                    return {"status": "cancelled"}

                repo_doc = saved_repos[repo_name]
                repo_id = repo_doc["_id"]
                ci_provider_value = repo_doc.get("ci_provider", dataset.ci_provider)

                ci_provider = get_ci_provider(ci_provider_value, db)

                db.enrichment_repositories.update_one(
                    {"_id": repo_id}, {"$set": {"builds_total": len(builds)}}
                )
                stats.repos_valid += 1

                builds_found = 0
                builds_not_found = 0

                for build_id in builds:
                    cancelled = redis.get(f"dataset_validation:{dataset_id}:cancelled")
                    if cancelled:
                        _update_status(db, dataset_id, "cancelled")
                        return {"status": "cancelled"}

                    # Check if build already validated
                    existing_build = db.dataset_builds.find_one(
                        {
                            "dataset_id": ObjectId(dataset_id),
                            "build_id_from_csv": build_id,
                            "repo_id": repo_id,
                        }
                    )

                    if existing_build and existing_build.get("status") in [
                        "found",
                        "not_found",
                    ]:
                        if existing_build.get("status") == "found":
                            builds_found += 1
                            stats.builds_found += 1
                        else:
                            builds_not_found += 1
                            stats.builds_not_found += 1
                        builds_processed += 1
                        continue

                    dataset_build = DatasetBuild(
                        dataset_id=ObjectId(dataset_id),
                        build_id_from_csv=build_id,
                        repo_name_from_csv=repo_name,
                        repo_id=repo_id,
                    )

                    try:
                        workflow_data = await ci_provider.get_workflow_run(
                            repo_name, int(build_id)
                        )
                        if workflow_data and ci_provider.is_run_completed(
                            workflow_data
                        ):
                            workflow_run = WorkflowRunRaw(
                                repo_id=repo_id,
                                workflow_run_id=int(build_id),
                                ci_provider=ci_provider_value,
                                head_sha=workflow_data.get("head_sha", ""),
                                run_number=workflow_data.get("run_number", 0),
                                status=workflow_data.get("status", "unknown"),
                                conclusion=workflow_data.get("conclusion", ""),
                                branch=workflow_data.get("head_branch", ""),
                                ci_created_at=workflow_data.get("created_at")
                                or datetime.utcnow(),
                                ci_updated_at=workflow_data.get("updated_at")
                                or datetime.utcnow(),
                                raw_payload=workflow_data,
                            )
                            wr_result = db.workflow_runs.insert_one(
                                workflow_run.model_dump(by_alias=True)
                            )

                            dataset_build.status = DatasetBuildStatus.FOUND
                            dataset_build.workflow_run_id = wr_result.inserted_id
                            dataset_build.validated_at = datetime.utcnow()
                            builds_found += 1
                            stats.builds_found += 1
                        else:
                            dataset_build.status = DatasetBuildStatus.NOT_FOUND
                            dataset_build.validation_error = (
                                "Build found but not completed"
                                if workflow_data
                                else "Build not found"
                            )
                            dataset_build.validated_at = datetime.utcnow()
                            builds_not_found += 1
                            stats.builds_not_found += 1
                    except Exception as e:
                        dataset_build.status = DatasetBuildStatus.ERROR
                        dataset_build.validation_error = str(e)
                        dataset_build.validated_at = datetime.utcnow()
                        builds_not_found += 1
                        stats.builds_not_found += 1

                    db.dataset_builds.insert_one(
                        dataset_build.model_dump(by_alias=True)
                    )
                    builds_processed += 1

                # Update repo build statistics
                db.enrichment_repositories.update_one(
                    {"_id": repo_id},
                    {
                        "$set": {
                            "builds_found": builds_found,
                            "builds_not_found": builds_not_found,
                        }
                    },
                )

                repos_processed += 1

                # Update progress
                progress = (
                    int((repos_processed / total_repos) * 100)
                    if total_repos > 0
                    else 100
                )
                db.datasets.update_one(
                    {"_id": ObjectId(dataset_id)},
                    {
                        "$set": {
                            "validation_progress": progress,
                            "validation_stats": stats.model_dump(),
                        }
                    },
                )

                try:
                    redis.publish(
                        f"dataset:{dataset_id}:validation",
                        str(
                            {
                                "progress": progress,
                                "repos_processed": repos_processed,
                                "repos_total": total_repos,
                                "builds_processed": builds_processed,
                                "builds_total": total_builds,
                                "current_repo": repo_name,
                            }
                        ),
                    )
                except Exception:
                    pass

            # Complete validation
            db.datasets.update_one(
                {"_id": ObjectId(dataset_id)},
                {
                    "$set": {
                        "validation_status": "completed",
                        "validation_completed_at": datetime.utcnow(),
                        "validation_progress": 100,
                        "validation_stats": stats.model_dump(),
                    }
                },
            )

            return {"status": "completed", "stats": stats.model_dump()}

        except Exception as e:
            logger.exception(f"Dataset validation failed: {e}")
            db.datasets.update_one(
                {"_id": ObjectId(dataset_id)},
                {
                    "$set": {
                        "validation_status": "failed",
                        "validation_completed_at": datetime.utcnow(),
                        "validation_error": str(e),
                    }
                },
            )
            # Re-raise to ensure celery marks it as failed (optional, but good for tracking)
            raise

    return asyncio.run(_do_validate())


def _update_status(db, dataset_id: str, status: str):
    db.datasets.update_one(
        {"_id": ObjectId(dataset_id)},
        {
            "$set": {
                "validation_status": status,
                "validation_completed_at": datetime.utcnow(),
            }
        },
    )
