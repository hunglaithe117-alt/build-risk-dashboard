"""Celery tasks for downloading and parsing workflow job logs."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime
from typing import Dict, List, Optional

from celery import chord, group

from app.celery_app import celery_app
from app.services.artifact_store import ArtifactStore
from app.services.log_parser import TestLogParser
from app.tasks.base import PipelineTask


parser = TestLogParser()
artifact_store = ArtifactStore()


def _unpack_zip(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        parts: List[str] = []
        for item in archive.infolist():
            with archive.open(item) as handle:
                parts.append(handle.read().decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def _duration_seconds(job_doc: Dict[str, object]) -> Optional[float]:
    started = job_doc.get("started_at")
    completed = job_doc.get("completed_at")
    if isinstance(started, str):
        started = datetime.fromisoformat(started.replace("Z", "+00:00"))
    if isinstance(completed, str):
        completed = datetime.fromisoformat(completed.replace("Z", "+00:00"))
    if started and completed:
        return (completed - started).total_seconds()
    return None


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.logs.collect_log_artifacts")
def collect_log_artifacts(self: PipelineTask, build_id: int, repository: str, job_id: Optional[str] = None) -> Dict[str, int]:
    """Download workflow job logs, persist them locally, and fan out parsing tasks."""

    jobs = list(self.db.workflow_jobs.find({"run_id": build_id}))
    repo_doc = self.db.repositories.find_one({"full_name": repository}) or {}
    metadata = repo_doc.get("metadata") or {}
    repo_lang = repo_doc.get("main_lang") or metadata.get("language")

    signatures = []
    job_ids: List[str] = []
    with self.github_client_for_repository(repository) as gh:
        if not jobs:
            workflow_jobs = gh.list_workflow_jobs(repository, build_id)
            self.store.record_workflow_jobs(build_id, workflow_jobs)
            jobs = list(self.db.workflow_jobs.find({"run_id": build_id}))

        for job in jobs:
            workflow_job_id = job.get("_id") or job.get("id")
            if workflow_job_id is None:
                continue
            job_ids.append(str(workflow_job_id))
            blob = gh.download_job_logs(repository, workflow_job_id)
            unpacked = _unpack_zip(blob)
            artifact_store.write_job_log(build_id, workflow_job_id, unpacked)
            signatures.append(
                parse_job_log.s(build_id, workflow_job_id, repository, repo_lang, job_id)
            )

    if job_ids:
        self.store.update_build_features(build_id, tr_job_ids=job_ids, tr_log_num_jobs=len(job_ids))
    else:
        summarize_build.delay([], build_id, repository, job_id)
        return {"jobs_enqueued": 0}

    if signatures:
        chord(group(signatures))(summarize_build.s(build_id, repository, job_id))
    else:
        summarize_build.delay([], build_id, repository, job_id)

    if job_id:
        self.store.update_import_job(job_id, progress=80, notes="Downloaded logs and scheduled parser")

    return {"jobs_enqueued": len(signatures)}


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.logs.parse_job_log")
def parse_job_log(
    self: PipelineTask,
    build_id: int,
    workflow_job_id: int,
    repository: str,
    language: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, object]:
    """Parse a single job log and accumulate aggregated counters."""

    log_text = artifact_store.read_job_log(build_id, workflow_job_id)
    parsed = parser.parse(log_text, language)
    job_doc = self.db.workflow_jobs.find_one({"_id": workflow_job_id}) or {}
    job_duration = _duration_seconds(job_doc) or parsed.duration_seconds or 0.0

    metrics = {
        "framework": parsed.framework,
        "language": parsed.language or language,
        "tests_run": parsed.tests_run,
        "tests_failed": parsed.tests_failed,
        "tests_skipped": parsed.tests_skipped,
        "tests_ok": parsed.tests_ok,
        "duration_seconds": job_duration,
        "test_duration_seconds": parsed.test_duration_seconds,
    }
    self.store.record_build_feature_block(build_id, f"log_jobs.{workflow_job_id}", metrics)
    return {
        "job_id": workflow_job_id,
        "tests_run": parsed.tests_run,
        "tests_failed": parsed.tests_failed,
        "tests_skipped": parsed.tests_skipped,
        "tests_ok": parsed.tests_ok,
        "framework": parsed.framework,
        "language": parsed.language or language,
        "build_duration": job_duration,
        "test_duration": parsed.test_duration_seconds or 0.0,
    }


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.logs.summarize_build")
def summarize_build(
    self: PipelineTask,
    results: List[Dict[str, object]],
    build_id: int,
    repository: str,
    job_id: Optional[str] = None,
) -> Dict[str, object]:
    """Finalize aggregated log metrics once every job log has been parsed."""

    job_ids = [str(item.get("job_id")) for item in results if item.get("job_id") is not None]
    total_jobs = len(job_ids)
    tests_run = sum(item.get("tests_run", 0) or 0 for item in results)
    tests_failed = sum(item.get("tests_failed", 0) or 0 for item in results)
    tests_skipped = sum(item.get("tests_skipped", 0) or 0 for item in results)
    tests_ok = sum(item.get("tests_ok", 0) or 0 for item in results)
    build_duration_sum = sum(item.get("build_duration", 0.0) or 0.0 for item in results)
    test_duration_sum = sum(item.get("test_duration", 0.0) or 0.0 for item in results)
    languages = sorted({item.get("language") for item in results if item.get("language")})
    frameworks = sorted({item.get("framework") for item in results if item.get("framework")})

    jobs_with_test_duration = len([item for item in results if item.get("test_duration")])
    fail_rate = float(tests_failed / tests_run) if tests_run else 0.0
    build_duration_mean = (build_duration_sum / total_jobs) if total_jobs else None
    test_duration_mean = (test_duration_sum / jobs_with_test_duration) if jobs_with_test_duration else None

    updates = {
        "tr_job_ids": job_ids,
        "tr_log_num_jobs": total_jobs,
        "tr_log_tests_run_sum": tests_run,
        "tr_log_tests_failed_sum": tests_failed,
        "tr_log_tests_skipped_sum": tests_skipped,
        "tr_log_tests_ok_sum": tests_ok,
        "tr_log_tests_fail_rate": fail_rate,
        "tr_log_buildduration_sum": build_duration_sum,
        "tr_log_buildduration_mean": build_duration_mean,
        "tr_log_testduration_sum": test_duration_sum,
        "tr_log_testduration_mean": test_duration_mean,
        "tr_log_lan_all": languages,
        "tr_log_frameworks_all": frameworks,
    }
    if languages:
        updates["tr_log_lang"] = languages[0]
    self.store.update_build_features(build_id, **updates)

    if job_id:
        self.store.update_import_job(job_id, progress=92, notes="Aggregated test logs")

    return {"build_id": build_id, "log_jobs": total_jobs}
