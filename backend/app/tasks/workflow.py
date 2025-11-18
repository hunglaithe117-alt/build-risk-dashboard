"""Workflow polling tasks."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from app.celery_app import celery_app
from app.tasks.base import PipelineTask


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:  # pragma: no cover - GitHub provides ISO timestamps
        return None


MAX_PAGES = 15


@celery_app.task(bind=True, base=PipelineTask, name="app.tasks.workflow.poll_workflow_runs")
def poll_workflow_runs(
    self: PipelineTask,
    repository: str,
    branch: Optional[str],
    cursor: Optional[str] = None,
    job_id: Optional[str] = None,
    page: int = 1,
) -> Dict[str, object]:
    """Poll workflow runs for a repository and enqueue build ingestion tasks."""

    cursor_doc = self.store.get_workflow_cursor(repository, branch or "")
    last_seen_started_at = None
    if cursor:
        last_seen_started_at = _parse_iso(cursor)
    elif cursor_doc:
        last_seen_started_at = cursor_doc.get("last_run_started_at")

    ingested_runs: List[int] = []
    skipped_due_to_logs = 0
    current_page = page

    with self.github_client() as gh:
        per_page = 50
        newest_run: Dict[str, object] | None = None

        while current_page <= MAX_PAGES:
            params = {"per_page": per_page, "page": current_page}
            if branch:
                params["branch"] = branch
            workflow_runs = gh.list_workflow_runs(repository, params=params)
            if not workflow_runs:
                break

            for run in workflow_runs:
                run_started_at = _parse_iso(run.get("run_started_at")) or _parse_iso(run.get("created_at"))
                if last_seen_started_at and run_started_at and run_started_at <= last_seen_started_at:
                    continue

                run_id = run.get("id")
                if not run_id:
                    continue

                actor = run.get("actor") or {}
                actor_login = None
                if isinstance(actor, dict):
                    actor_login = (actor.get("login") or "").lower()
                elif isinstance(actor, str):  # pragma: no cover - defensive
                    actor_login = actor.lower()

                if actor_login and "dependabot" in actor_login:
                    continue

                if not gh.logs_available(repository, run_id):
                    skipped_due_to_logs += 1
                    continue

                payload = {
                    "_id": run_id,
                    "repository": repository,
                    "branch": run.get("head_branch"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "event": run.get("event"),
                    "created_at": _parse_iso(run.get("created_at")),
                    "started_at": run_started_at,
                    "updated_at": _parse_iso(run.get("updated_at")),
                    "logs_url": run.get("logs_url"),
                    "check_suite_id": run.get("check_suite_id"),
                    "display_title": run.get("display_title"),
                    "head_sha": run.get("head_sha"),
                    "actor": run.get("actor"),
                    "pull_requests": run.get("pull_requests", []),
                }
                self.store.upsert_workflow_run(run_id, payload)
                ingest_workflow_run.delay(repository, run_id, job_id)
                ingested_runs.append(run_id)
                if newest_run is None:
                    newest_run = run

            if len(workflow_runs) < per_page:
                break
            current_page += 1

    if ingested_runs and newest_run:
        newest_started = _parse_iso(newest_run.get("run_started_at")) or _parse_iso(newest_run.get("created_at"))
        if newest_started:
            self.store.update_workflow_cursor(repository, branch or "", newest_run.get("id"), newest_started)

    if job_id:
        progress = min(40, 10 + len(ingested_runs) * 3)
        if ingested_runs:
            notes = f"Đang thu {len(ingested_runs)} build còn log"
        else:
            notes = "Không tìm thấy build với log còn tồn tại"
            if skipped_due_to_logs:
                notes += f" (bỏ qua {skipped_due_to_logs} build hết log)"
        self.store.update_import_job(job_id, status="running", progress=progress, notes=notes)

    return {
        "repository": repository,
        "runs_enqueued": len(ingested_runs),
        "runs_missing_logs": skipped_due_to_logs,
        "pages_scanned": min(MAX_PAGES, max(page, current_page)),
    }


from app.tasks.builds import ingest_workflow_run  # noqa: E402  (circular import guard)
