"""
Training Pipeline - Ingestion Tasks (Phase 1)

This module handles the ingestion phase of training scenario:
1. start_scenario_ingestion - Orchestrator: Filter + Ingest builds
2. filter_scenario_builds - Query RawRepository + RawBuildRun by config
3. aggregate_scenario_ingestion - Chord callback: aggregate ingestion results
4. handle_scenario_chord_error - Error handler for ingestion failures
5. reingest_failed_builds - Retry FAILED builds

After ingestion completes, scenario is marked as INGESTED.
User triggers Phase 2 (processing) manually via start_scenario_processing.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List

from bson import ObjectId
from celery import chord, group

from app.celery_app import celery_app
from app.entities.training_ingestion_build import (
    IngestionStatus,
    TrainingIngestionBuild,
)
from app.entities.training_scenario import ScenarioStatus, TrainingScenario
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.repositories.training_ingestion_build import TrainingIngestionBuildRepository
from app.repositories.training_scenario import TrainingScenarioRepository
from app.tasks.base import PipelineTask
from app.tasks.shared.events import publish_scenario_update

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_ingestion.start_scenario_ingestion",
    queue="scenario_ingestion",
    soft_time_limit=120,
    time_limit=180,
)
def start_scenario_ingestion(
    self: PipelineTask,
    scenario_id: str,
) -> Dict[str, Any]:
    """
    Orchestrator: Start training scenario ingestion phase.

    Flow:
        start_scenario_ingestion
            └── filter_scenario_builds
                └── chord(
                        group(ingestion_chain_1, ingestion_chain_2, ...),
                        aggregate_scenario_ingestion
                    )

    After ingestion completes, scenario is marked as INGESTED.
    User triggers processing (Phase 2) manually via start_scenario_processing.
    """
    from app.tasks.pipeline.resource_dag import get_ingestion_tasks_by_level
    from app.tasks.shared import TrainingPipelineContext, build_workflow_with_context

    correlation_id = str(uuid.uuid4())
    logger.info(
        f"[start_scenario_ingestion] Starting scenario {scenario_id}, corr={correlation_id[:8]}"
    )

    scenario_repo = TrainingScenarioRepository(self.db)
    raw_repo_repo = RawRepositoryRepository(self.db)
    raw_build_run_repo = RawBuildRunRepository(self.db)

    # Load scenario
    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        logger.error(f"Scenario {scenario_id} not found")
        return {"status": "error", "error": "Scenario not found"}

    try:
        # Step 1: Filter builds from RawRepository + RawBuildRun
        filter_result = _filter_builds_for_scenario(
            db=self.db,
            scenario=scenario,
            scenario_id=scenario_id,
            correlation_id=correlation_id,
        )

        if filter_result["status"] == "error":
            scenario_repo.update_one(
                scenario_id,
                {
                    "status": ScenarioStatus.FAILED.value,
                    "error_message": filter_result["error"],
                },
            )
            return filter_result

        builds_total = filter_result["builds_total"]
        ingestion_build_ids = filter_result["ingestion_build_ids"]
        builds_by_repo = filter_result["builds_by_repo"]

        # Update status to INGESTING
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.INGESTING.value,
                "filtering_started_at": datetime.utcnow(),
                "ingestion_started_at": datetime.utcnow(),
                "builds_total": builds_total,
                "current_task_id": self.request.id,
                "error_message": None,
            },
        )

        # Publish SSE event for UI update
        publish_scenario_update(
            scenario_id=scenario_id,
            status=ScenarioStatus.INGESTING.value,
            builds_total=builds_total,
            current_phase="Ingesting build data (clone, worktree, logs)",
        )

        if not builds_by_repo:
            # No ingestion needed
            logger.info("[start_scenario_ingestion] No ingestion chains needed")
            ingestion_build_repo = TrainingIngestionBuildRepository(self.db)

            # Mark all as INGESTED
            for build_id in ingestion_build_ids:
                ingestion_build_repo.update_status(build_id, IngestionStatus.INGESTED)

            scenario_repo.update_one(
                scenario_id,
                {
                    "status": ScenarioStatus.INGESTED.value,
                    "builds_ingested": len(ingestion_build_ids),
                    "ingestion_completed_at": datetime.utcnow(),
                },
            )
            publish_scenario_update(
                scenario_id=scenario_id,
                status=ScenarioStatus.INGESTED.value,
                builds_total=builds_total,
                builds_ingested=len(ingestion_build_ids),
                current_phase="Ingestion complete. Start processing when ready.",
            )
            return {
                "status": "completed",
                "message": "Ingestion complete. Start processing when ready.",
            }

        # Step 2: Build ingestion chains
        required_resources = ["git_history", "git_worktree", "build_logs"]
        tasks_by_level = get_ingestion_tasks_by_level(required_resources)

        ingestion_chains = []
        repo_metadata = []

        for raw_repo_id, repo_builds in builds_by_repo.items():
            raw_repo = raw_repo_repo.find_by_id(raw_repo_id)
            if not raw_repo:
                logger.warning(
                    f"[start_scenario_ingestion] Repo {raw_repo_id} not found, skipping"
                )
                continue

            # Get build IDs and commit SHAs
            build_ids = [b["ci_run_id"] for b in repo_builds if b.get("ci_run_id")]
            commit_shas = list(
                {b["commit_sha"] for b in repo_builds if b.get("commit_sha")}
            )

            if not build_ids:
                continue

            # Create context for this repo
            ctx = TrainingPipelineContext(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                _raw_repo_id=raw_repo_id,
                _github_repo_id=raw_repo.github_repo_id,
                _full_name=raw_repo.full_name,
            )

            # Build ingestion chain for this repo
            repo_chain = build_workflow_with_context(
                tasks_by_level=tasks_by_level,
                ctx=ctx,
                raw_repo_id=raw_repo_id,
                github_repo_id=raw_repo.github_repo_id,
                full_name=raw_repo.full_name,
                build_ids=build_ids,
                commit_shas=commit_shas,
                ci_provider="github_actions",
            )

            if repo_chain:
                ingestion_chains.append(repo_chain)
                repo_metadata.append(
                    {
                        "raw_repo_id": raw_repo_id,
                        "full_name": raw_repo.full_name,
                        "builds": len(build_ids),
                        "commits": len(commit_shas),
                    }
                )

        if not ingestion_chains:
            # Mark all as INGESTED
            ingestion_build_repo = TrainingIngestionBuildRepository(self.db)
            for build_id in ingestion_build_ids:
                ingestion_build_repo.update_status(build_id, IngestionStatus.INGESTED)

            scenario_repo.update_one(
                scenario_id,
                {
                    "status": ScenarioStatus.INGESTED.value,
                    "builds_ingested": len(ingestion_build_ids),
                    "ingestion_completed_at": datetime.utcnow(),
                },
            )
            return {
                "status": "completed",
                "message": "Ingestion complete. Start processing when ready.",
            }

        # Step 3: Initialize resource status
        ingestion_build_repo = TrainingIngestionBuildRepository(self.db)
        ingestion_build_repo.collection.update_many(
            {
                "scenario_id": ObjectId(scenario_id),
                "status": IngestionStatus.PENDING.value,
            },
            {"$set": {"status": IngestionStatus.INGESTING.value}},
        )

        # Step 4: Dispatch chord
        callback = aggregate_scenario_ingestion.s(
            scenario_id=scenario_id,
            correlation_id=correlation_id,
        )

        error_callback = handle_scenario_chord_error.s(
            scenario_id=scenario_id,
            correlation_id=correlation_id,
        )

        callback_with_error = callback.on_error(error_callback)
        chord(group(ingestion_chains), callback_with_error).apply_async()

        logger.info(
            f"[start_scenario_ingestion] Dispatched {len(ingestion_chains)} ingestion chains"
        )

        return {
            "status": "dispatched",
            "builds_total": builds_total,
            "ingestion_chains": len(ingestion_chains),
            "repo_metadata": repo_metadata,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Scenario ingestion start failed: {error_msg}")
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.FAILED.value,
                "error_message": error_msg,
            },
        )
        raise


def _filter_builds_for_scenario(
    db,
    scenario: TrainingScenario,
    scenario_id: str,
    correlation_id: str,
) -> Dict[str, Any]:
    """
    Filter and create IngestionBuild records from RawRepository + RawBuildRun.

    Returns dict with:
        - status: "completed" or "error"
        - builds_total: number of builds found
        - ingestion_build_ids: list of created IngestionBuild IDs
        - builds_by_repo: dict mapping repo_id -> list of build info
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    ingestion_build_repo = TrainingIngestionBuildRepository(db)
    raw_repo_repo = RawRepositoryRepository(db)
    raw_build_run_repo = RawBuildRunRepository(db)

    # Build query from data_source_config
    data_config = scenario.data_source_config
    if isinstance(data_config, dict):
        config_dict = data_config
    else:
        config_dict = (
            data_config.model_dump()
            if hasattr(data_config, "model_dump")
            else data_config.__dict__
        )

    # Helper to get value from flat key or nested section
    def get_cfg(key, section=None, subkey=None, default=None):
        if key in config_dict and config_dict[key] is not None:
            return config_dict[key]
        if section and section in config_dict:
            section_dict = config_dict[section]
            if isinstance(section_dict, dict) and subkey in section_dict:
                return section_dict[subkey]
        return default

    filter_by = get_cfg("filter_by", "repositories", "filter_by", "all")
    languages = get_cfg("languages", "repositories", "languages", [])
    repo_names = get_cfg("repo_names", "repositories", "repo_names", [])
    owners = get_cfg("owners", "repositories", "owners", [])

    # Builds config
    conclusions = get_cfg(
        "conclusions", "builds", "conclusions", ["success", "failure"]
    )
    exclude_bots = get_cfg("exclude_bots", "builds", "exclude_bots", True)

    # Date range handling
    date_start = config_dict.get("date_start")
    date_end = config_dict.get("date_end")

    if not date_start and "builds" in config_dict:
        builds_cfg = config_dict["builds"]
        if isinstance(builds_cfg, dict) and "date_range" in builds_cfg:
            date_range = builds_cfg["date_range"]
            if isinstance(date_range, dict):
                date_start = date_range.get("start")
                date_end = date_range.get("end")

    # Query public repositories
    repo_query: Dict[str, Any] = {"is_private": False}

    if filter_by == "by_language" and languages:
        repo_query["main_lang"] = {"$in": [lang.lower() for lang in languages]}
    elif filter_by == "by_name" and repo_names:
        repo_query["full_name"] = {"$in": repo_names}
    elif filter_by == "by_owner" and owners:
        repo_query["$or"] = [{"full_name": {"$regex": f"^{o}/"}} for o in owners]

    repos = raw_repo_repo.find_many(repo_query)
    repo_ids = [str(r.id) for r in repos]

    if not repo_ids:
        logger.warning(f"{corr_prefix} [filter] No repos match filter criteria")
        return {"status": "error", "error": "No repositories match filter criteria"}

    logger.info(f"{corr_prefix} [filter] Found {len(repo_ids)} matching repos")

    # Query builds for these repos
    build_query: Dict[str, Any] = {
        "raw_repo_id": {"$in": [ObjectId(rid) for rid in repo_ids]},
    }

    # Filter by conclusion
    if conclusions:
        build_query["conclusion"] = {"$in": conclusions}

    # Filter by date range
    if date_start or date_end:
        date_filter = {}
        if date_start:
            date_filter["$gte"] = (
                date_start
                if isinstance(date_start, datetime)
                else datetime.fromisoformat(str(date_start))
            )
        if date_end:
            date_filter["$lte"] = (
                date_end
                if isinstance(date_end, datetime)
                else datetime.fromisoformat(str(date_end))
            )
        if date_filter:
            build_query["started_at"] = date_filter

    # Exclude bot commits
    if exclude_bots:
        build_query["$and"] = [
            {"actor_login": {"$not": {"$regex": "\\[bot\\]$", "$options": "i"}}},
            {"actor_login": {"$not": {"$regex": "-bot$", "$options": "i"}}},
        ]

    builds = raw_build_run_repo.find_many(build_query)

    if not builds:
        logger.warning(f"{corr_prefix} [filter] No builds match filter criteria")
        return {"status": "error", "error": "No builds match filter criteria"}

    logger.info(f"{corr_prefix} [filter] Found {len(builds)} matching builds")

    # Create IngestionBuild records and group by repo
    repo_cache = {str(r.id): r for r in repos}
    builds_by_repo: Dict[str, List[Dict[str, Any]]] = {}
    ingestion_build_ids = []
    required_resources = ["git_history", "git_worktree", "build_logs"]

    for build in builds:
        repo = repo_cache.get(str(build.raw_repo_id))
        repo_id = str(build.raw_repo_id)

        # Create IngestionBuild record
        ingestion_build = TrainingIngestionBuild(
            scenario_id=ObjectId(scenario_id),
            raw_repo_id=build.raw_repo_id,
            raw_build_run_id=build.id,
            ci_run_id=build.ci_run_id or "",
            commit_sha=build.commit_sha or "",
            repo_full_name=repo.full_name if repo else "",
            github_repo_id=repo.github_repo_id if repo else None,
            status=IngestionStatus.PENDING,
            required_resources=required_resources,
            resource_status={},
        )

        created = ingestion_build_repo.insert_one(ingestion_build)
        ingestion_build_ids.append(str(created.id))

        # Group for ingestion chains
        build_info = {
            "ingestion_build_id": str(created.id),
            "ci_run_id": build.ci_run_id or "",
            "commit_sha": build.commit_sha or "",
        }

        if repo_id not in builds_by_repo:
            builds_by_repo[repo_id] = []
        builds_by_repo[repo_id].append(build_info)

    logger.info(
        f"{corr_prefix} [filter] Created {len(ingestion_build_ids)} ingestion build records"
    )

    return {
        "status": "completed",
        "builds_total": len(builds),
        "ingestion_build_ids": ingestion_build_ids,
        "builds_by_repo": builds_by_repo,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_ingestion.aggregate_scenario_ingestion",
    queue="scenario_ingestion",
    soft_time_limit=120,
    time_limit=180,
)
def aggregate_scenario_ingestion(
    self: PipelineTask,
    results: List[Dict[str, Any]],
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Chord callback: Aggregate ingestion results and mark scenario as INGESTED.

    After all repo ingestion chains complete, marks builds as INGESTED/FAILED.
    Does NOT auto-dispatch processing - user triggers Phase 2 manually.
    """
    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""
    logger.info(
        f"{corr_prefix} [aggregate_ingestion] Processing results for {scenario_id}"
    )

    scenario_repo = TrainingScenarioRepository(self.db)
    ingestion_build_repo = TrainingIngestionBuildRepository(self.db)

    now = datetime.utcnow()

    # Determine per-build final status from resource_status in DB
    # FAILED: Any required resource has status = "failed" (actual error - RETRYABLE)
    # MISSING_RESOURCE: Logs expired (expected - NOT RETRYABLE)
    # INGESTED: All required resources completed

    # 1. Check if git_history failed (affects ALL builds)
    git_history_failed = ingestion_build_repo.collection.count_documents(
        {
            "scenario_id": ObjectId(scenario_id),
            "status": IngestionStatus.INGESTING.value,
            "resource_status.git_history.status": "failed",
        }
    )

    if git_history_failed > 0:
        # Clone failed - mark all as FAILED
        ingestion_build_repo.collection.update_many(
            {
                "scenario_id": ObjectId(scenario_id),
                "status": IngestionStatus.INGESTING.value,
            },
            {
                "$set": {
                    "status": IngestionStatus.FAILED.value,
                    "ingestion_error": "Clone failed",
                    "ingested_at": now,
                }
            },
        )
    else:
        # 2. Mark builds with failed git_worktree as FAILED
        ingestion_build_repo.collection.update_many(
            {
                "scenario_id": ObjectId(scenario_id),
                "status": IngestionStatus.INGESTING.value,
                "resource_status.git_worktree.status": "failed",
            },
            {
                "$set": {
                    "status": IngestionStatus.FAILED.value,
                    "ingestion_error": "Worktree creation failed",
                    "ingested_at": now,
                }
            },
        )

        # 3. Mark builds with failed build_logs as MISSING_RESOURCE
        ingestion_build_repo.collection.update_many(
            {
                "scenario_id": ObjectId(scenario_id),
                "status": IngestionStatus.INGESTING.value,
                "resource_status.build_logs.status": "failed",
            },
            {
                "$set": {
                    "status": IngestionStatus.MISSING_RESOURCE.value,
                    "ingestion_error": "Log download failed or expired",
                    "ingested_at": now,
                }
            },
        )

        # 4. Mark remaining INGESTING builds as INGESTED
        ingestion_build_repo.collection.update_many(
            {
                "scenario_id": ObjectId(scenario_id),
                "status": IngestionStatus.INGESTING.value,
            },
            {
                "$set": {
                    "status": IngestionStatus.INGESTED.value,
                    "ingested_at": now,
                }
            },
        )

    # Count by status
    status_counts = ingestion_build_repo.count_by_status(scenario_id)
    ingested = status_counts.get(IngestionStatus.INGESTED.value, 0)
    missing_resource = status_counts.get(IngestionStatus.MISSING_RESOURCE.value, 0)
    failed = status_counts.get(IngestionStatus.FAILED.value, 0)
    total_builds = ingested + missing_resource + failed

    # Update scenario
    scenario_repo.update_one(
        scenario_id,
        {
            "status": ScenarioStatus.INGESTED.value,
            "builds_ingested": ingested,
            "builds_missing_resource": missing_resource,
            "builds_failed": failed,
            "ingestion_completed_at": now,
        },
    )

    # Build status message
    if failed > 0 or missing_resource > 0:
        parts = [f"{ingested} ready"]
        if failed > 0:
            parts.append(f"{failed} failed (retryable)")
        if missing_resource > 0:
            parts.append(f"{missing_resource} missing resources")
        msg = f"Ingestion done: {', '.join(parts)}. Start processing when ready."
    else:
        msg = (
            f"Ingestion complete: {ingested} builds ready. Start processing when ready."
        )

    logger.info(f"{corr_prefix} [aggregate_ingestion] {msg}")

    # Publish event for frontend
    publish_scenario_update(
        scenario_id=scenario_id,
        status=ScenarioStatus.INGESTED.value,
        builds_total=total_builds,
        builds_ingested=ingested,
        builds_missing_resource=missing_resource,
        builds_failed=failed,
        current_phase=msg,
    )

    return {
        "status": "completed",
        "final_status": ScenarioStatus.INGESTED.value,
        "builds_ingested": ingested,
        "builds_missing_resource": missing_resource,
        "builds_failed": failed,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_ingestion.handle_scenario_chord_error",
    queue="scenario_ingestion",
    soft_time_limit=60,
    time_limit=120,
)
def handle_scenario_chord_error(
    self: PipelineTask,
    task_id: str,
    scenario_id: str,
    correlation_id: str = "",
) -> Dict[str, Any]:
    """
    Error callback for ingestion chord failure.
    """
    from celery.result import AsyncResult

    corr_prefix = f"[corr={correlation_id[:8]}]" if correlation_id else ""

    # Try to get error info
    error_msg = "Unknown ingestion error"
    try:
        result = AsyncResult(task_id)
        if isinstance(result.result, Exception):
            error_msg = str(result.result)
        elif result.result:
            error_msg = str(result.result)
    except Exception as e:
        logger.warning(f"Could not retrieve exception for task {task_id}: {e}")

    logger.error(
        f"{corr_prefix} Ingestion chord failed for scenario {scenario_id}: {error_msg}"
    )

    ingestion_build_repo = TrainingIngestionBuildRepository(self.db)
    scenario_repo = TrainingScenarioRepository(self.db)

    now = datetime.utcnow()

    # Mark all INGESTING builds as FAILED
    failed_count = ingestion_build_repo.collection.update_many(
        {
            "scenario_id": ObjectId(scenario_id),
            "status": IngestionStatus.INGESTING.value,
        },
        {
            "$set": {
                "status": IngestionStatus.FAILED.value,
                "ingestion_error": f"Ingestion chord failed: {error_msg}",
                "ingested_at": now,
            }
        },
    ).modified_count

    # Check if any builds made it to INGESTED
    ingested_count = ingestion_build_repo.collection.count_documents(
        {
            "scenario_id": ObjectId(scenario_id),
            "status": IngestionStatus.INGESTED.value,
        }
    )

    if ingested_count > 0:
        # Some builds made it through
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.INGESTED.value,
                "builds_ingested": ingested_count,
                "builds_failed": failed_count,
                "ingestion_completed_at": now,
            },
        )
        publish_scenario_update(
            scenario_id=scenario_id,
            status=ScenarioStatus.INGESTED.value,
            builds_ingested=ingested_count,
            builds_failed=failed_count,
        )
    else:
        # No builds made it
        scenario_repo.update_one(
            scenario_id,
            {
                "status": ScenarioStatus.FAILED.value,
                "error_message": error_msg,
            },
        )
        publish_scenario_update(
            scenario_id=scenario_id,
            status=ScenarioStatus.FAILED.value,
            error=error_msg,
        )

    return {
        "status": "handled",
        "failed_builds": failed_count,
        "ingested_builds": ingested_count,
        "error": error_msg,
    }


@celery_app.task(
    bind=True,
    base=PipelineTask,
    name="app.tasks.training_ingestion.reingest_failed_builds",
    queue="scenario_ingestion",
    soft_time_limit=300,
    time_limit=360,
)
def reingest_failed_builds(
    self: PipelineTask,
    scenario_id: str,
) -> Dict[str, Any]:
    """
    Re-ingest only FAILED ingestion builds for a scenario.

    Only retries builds with status=FAILED (actual errors like timeout, network failure).
    Does NOT retry MISSING_RESOURCE builds (expected - logs expired, commit not found).
    """
    correlation_id = str(uuid.uuid4())

    scenario_repo = TrainingScenarioRepository(self.db)
    ingestion_build_repo = TrainingIngestionBuildRepository(self.db)

    # Validate scenario exists
    scenario = scenario_repo.find_by_id(scenario_id)
    if not scenario:
        return {"status": "error", "message": "Scenario not found"}

    # Find FAILED builds (not MISSING_RESOURCE)
    failed_count = ingestion_build_repo.collection.count_documents(
        {
            "scenario_id": ObjectId(scenario_id),
            "status": IngestionStatus.FAILED.value,
        }
    )

    missing_count = ingestion_build_repo.collection.count_documents(
        {
            "scenario_id": ObjectId(scenario_id),
            "status": IngestionStatus.MISSING_RESOURCE.value,
        }
    )

    if failed_count == 0:
        msg = "No failed builds to retry"
        if missing_count > 0:
            msg += f" ({missing_count} builds have missing resources - not retryable)"
        return {
            "status": "no_failed_builds",
            "failed_count": 0,
            "missing_resource_count": missing_count,
            "message": msg,
        }

    # Reset FAILED builds to PENDING
    reset_result = ingestion_build_repo.collection.update_many(
        {
            "scenario_id": ObjectId(scenario_id),
            "status": IngestionStatus.FAILED.value,
        },
        {
            "$set": {
                "status": IngestionStatus.PENDING.value,
                "ingestion_error": None,
                "ingested_at": None,
                "resource_status": {},
            }
        },
    )

    if reset_result.modified_count == 0:
        return {"status": "error", "message": "Failed to reset any builds"}

    # Re-trigger ingestion
    start_scenario_ingestion.delay(scenario_id)

    logger.info(
        f"Re-triggered ingestion for {reset_result.modified_count} failed builds"
    )

    return {
        "status": "queued",
        "builds_reset": reset_result.modified_count,
        "total_failed": failed_count,
        "correlation_id": correlation_id,
    }
