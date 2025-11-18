"""Celery tasks that convert workflow runs into enriched build documents."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from celery import chain

from app.celery_app import celery_app
from app.services.pipeline_exceptions import PipelineRetryableError
from app.tasks.base import PipelineTask
from app.services.diff_analyzer import analyze_diff
from app.tasks.logs import collect_log_artifacts


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _word_count(*chunks: Optional[str]) -> int:
    joined = " ".join(filter(None, chunks))
    return len([token for token in joined.split() if token])


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.builds.ingest_workflow_run")
def ingest_workflow_run(self: PipelineTask, repository: str, run_id: int, job_id: Optional[str] = None) -> Dict[str, object]:
    """Materialize the base build document and fan-out enrichment tasks."""

    run = self.db.workflow_runs.find_one({"_id": run_id})
    if not run:
        raise PipelineRetryableError(f"Workflow run {run_id} not yet available in DB")

    started_at = run.get("started_at") or run.get("created_at")
    completed_at = run.get("updated_at") or started_at
    duration = None
    if started_at and completed_at:
        duration = int((completed_at - started_at).total_seconds())

    base_doc = {
        "_id": run_id,
        "repository": repository,
        "branch": run.get("branch") or run.get("head_branch"),
        "installation_id": run.get("installation_id"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration,
        "workflow_name": run.get("name"),
        "commit_sha": run.get("head_sha"),
        "build_number": str(run.get("run_number") or run_id),
        "url": run.get("html_url"),
        "logs_url": run.get("logs_url"),
    }
    self.store.upsert_build(run_id, base_doc)
    self.store.update_build_features(
        run_id,
        tr_build_id=run_id,
        gh_project_name=repository,
        gh_build_started_at=started_at,
        tr_build_number=run.get("run_number") or run.get("run_attempt") or run_id,
        tr_status=run.get("status"),
        tr_duration=duration,
        gh_is_pr=bool(run.get("pull_requests")),
        tr_original_commit=(run.get("head_commit") or {}).get("id") or run.get("head_sha"),
    )

    # Step 1: download workflow job logs before other enrichment tasks.
    collect_log_artifacts.delay(run_id, repository, job_id)

    enrichment_chain = chain(
        resolve_build_context.si(run_id, repository, job_id),
        resolve_commit_lineage.si(run_id, repository, job_id),
        aggregate_commit_activity.si(run_id, repository, job_id),
        compute_diff_metrics.si(run_id, repository, job_id),
    )
    enrichment_chain.delay()

    if job_id:
        self.store.update_import_job(job_id, progress=45, notes="Analyzing build metadata")

    return {"build_id": run_id, "repository": repository}


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.builds.resolve_build_context")
def resolve_build_context(self: PipelineTask, build_id: int, repository: str, job_id: Optional[str] = None) -> int:
    """Gather pull request metadata and workflow jobs."""

    with self.github_client_for_repository(repository) as gh:
        run_payload = gh.get_workflow_run(repository, build_id)
        workflow_jobs = gh.list_workflow_jobs(repository, build_id)

        pr_info = (run_payload.get("pull_requests") or [])
        pr_number = pr_info[0]["number"] if pr_info else None
        pr_payload = gh.get_pull_request(repository, pr_number) if pr_number else None

        repo_snapshot = self.db.repositories.find_one({"full_name": repository}) or {}
        metadata = repo_snapshot.get("metadata") or {}
        contributors = metadata.get("contributors") or []

        head_commit = run_payload.get("head_commit") or {}
        author_login = (head_commit.get("author") or {}).get("login") or (head_commit.get("committer") or {}).get("login")

    self.store.record_workflow_jobs(build_id, workflow_jobs)

    job_ids = [job.get("id") for job in workflow_jobs if job.get("id")]
    context_updates = {
        "git_branch": run_payload.get("head_branch"),
        "git_trigger_commit": run_payload.get("head_sha"),
        "tr_original_commit": run_payload.get("head_sha"),
        "gh_is_pr": bool(pr_number),
        "gh_pull_req_num": pr_number,
        "gh_pr_created_at": _parse_iso(pr_payload.get("created_at")) if pr_payload else None,
        "gh_description_complexity": _word_count(
            pr_payload.get("title") if pr_payload else None,
            pr_payload.get("body") if pr_payload else None,
        ),
        "gh_by_core_team_member": author_login in contributors if author_login else False,
        "tr_job_id": job_ids[0] if job_ids else None,
        "tr_job_ids": job_ids,
        "tr_log_num_jobs": len(workflow_jobs),
    }

    self.store.update_build_features(build_id, **context_updates)

    if job_id:
        self.store.update_import_job(job_id, progress=50, notes="Collected pull request metadata")

    return build_id


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.builds.resolve_commit_lineage")
def resolve_commit_lineage(self: PipelineTask, build_id: int, repository: str, job_id: Optional[str] = None) -> int:
    """Compute git lineage (trigger commit + commits included in this build)."""

    build = self.db.builds.find_one({"_id": build_id})
    if not build:
        raise PipelineRetryableError(f"Build {build_id} missing in DB")

    head_sha = build.get("git_trigger_commit")
    if not head_sha:
        run_doc = self.db.workflow_runs.find_one({"_id": build_id}) or {}
        head_sha = run_doc.get("head_sha")

    if not head_sha:
        raise PipelineRetryableError(f"Could not determine trigger commit for build {build_id}")

    branch = build.get("git_branch") or (self.db.workflow_runs.find_one({"_id": build_id}) or {}).get("head_branch")
    previous_build = (
        self.db.builds.find(
            {
                "repository": repository,
                "git_branch": branch,
                "_id": {"$ne": build_id},
                "gh_build_started_at": {"$lt": build.get("gh_build_started_at")},
            }
        )
        .sort("gh_build_started_at", -1)
        .limit(1)
    )
    previous_build_doc = next(previous_build, None)

    prev_sha = (previous_build_doc or {}).get("git_trigger_commit")
    commits: List[Dict[str, object]] = []

    with self.github_client_for_repository(repository) as gh:
        if prev_sha:
            comparison = gh.compare_commits(repository, prev_sha, head_sha)
            commits_payload = comparison.get("commits", [])
        else:
            commits_payload = [gh.get_commit(repository, head_sha)]

    for commit in commits_payload:
        sha = commit.get("sha")
        commit_info = commit.get("commit", {})
        stats = commit.get("stats", {})
        commits.append(
            {
                "sha": sha,
                "author": (commit_info.get("author") or {}).get("name"),
                "date": _parse_iso((commit_info.get("author") or {}).get("date")),
                "message": commit_info.get("message"),
                "additions": stats.get("additions"),
                "deletions": stats.get("deletions"),
            }
        )

    resolution_status = "build_found" if previous_build_doc else "baseline"
    updates = {
        "git_prev_commit_resolution_status": resolution_status,
        "git_prev_built_commit": prev_sha,
        "tr_prev_build": previous_build_doc.get("_id") if previous_build_doc else None,
    }
    self.store.append_build_commits(build_id, commits)
    self.store.update_build_features(build_id, **updates)

    if job_id:
        self.store.update_import_job(job_id, progress=55, notes="Resolved commit lineage")

    return build_id


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.builds.aggregate_commit_activity")
def aggregate_commit_activity(self: PipelineTask, build_id: int, repository: str, job_id: Optional[str] = None) -> int:
    """Aggregate GitHub discussions surrounding the build."""

    build = self.db.builds.find_one({"_id": build_id})
    if not build:
        raise PipelineRetryableError(f"Build {build_id} does not exist")

    commits = build.get("git_all_built_commits") or []
    pr_number = build.get("gh_pull_req_num")
    commit_comment_count = 0
    issue_comments_count = 0
    pr_comments_count = 0

    with self.github_client_for_repository(repository) as gh:
        for commit in commits:
            sha = commit.get("sha")
            if not sha:
                continue
            commit_comment_count += len(gh.list_commit_comments(repository, sha))

        if pr_number:
            issue_comments_count = len(gh.list_issue_comments(repository, pr_number))
            pr_comments_count = len(gh.list_review_comments(repository, pr_number))

    updates = {
        "gh_num_issue_comments": issue_comments_count,
        "gh_num_commit_comments": commit_comment_count,
        "gh_num_pr_comments": pr_comments_count,
        "gh_num_commits_on_files_touched": len(commits),
    }
    self.store.update_build_features(build_id, **updates)

    if job_id:
        self.store.update_import_job(job_id, progress=60, notes="Aggregated discussion activity")

    return build_id


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.builds.compute_diff_metrics")
def compute_diff_metrics(self: PipelineTask, build_id: int, repository: str, job_id: Optional[str] = None) -> int:
    """Compute churn and file-type metrics for the current build diff."""

    build = self.db.builds.find_one({"_id": build_id}) or {}
    features = build.get("features") or {}
    head_sha = features.get("git_trigger_commit")
    base_sha = features.get("git_prev_built_commit")

    if not head_sha:
        return build_id

    with self.github_client_for_repository(repository) as gh:
        if not base_sha:
            commit_doc = gh.get_commit(repository, head_sha)
            parents = commit_doc.get("parents") or []
            base_sha = parents[0].get("sha") if parents else head_sha

        if base_sha == head_sha:
            return build_id

        comparison = gh.compare_commits(repository, base_sha, head_sha)

    repo_doc = self.db.repositories.find_one({"full_name": repository}) or {}
    metadata = repo_doc.get("metadata") or {}
    language = repo_doc.get("main_lang") or metadata.get("language")
    diff_stats = analyze_diff(comparison.get("files", []), language)

    feature_updates = {
        **diff_stats,
        "gh_lang": language,
        "git_trigger_commit": head_sha,
    }

    filtered = {key: value for key, value in feature_updates.items() if value is not None}
    self.store.update_build_features(build_id, **filtered)

    if job_id:
        self.store.update_import_job(job_id, progress=75, notes="Computed diff/git metrics")

    return build_id
