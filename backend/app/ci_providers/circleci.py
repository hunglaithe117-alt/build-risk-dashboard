"""
CircleCI Provider - Fetches build data from CircleCI API.

This provider handles:
- Pipelines and workflows
- Jobs
- Build logs
"""

import logging
from datetime import datetime
from typing import List, Optional

import httpx

from app.config import settings

from .base import CIProviderInterface
from .factory import CIProviderRegistry
from .models import (
    BuildConclusion,
    BuildData,
    BuildStatus,
    CIProvider,
    JobData,
    LogFile,
)

logger = logging.getLogger(__name__)

CIRCLECI_API_BASE = "https://circleci.com/api/v2"

BOT_PATTERNS = ["[bot]", "dependabot", "renovate", "circleci", "github-actions"]


def _is_bot_author(author: Optional[str]) -> bool:
    if not author:
        return False
    return any(pattern in author.lower() for pattern in BOT_PATTERNS)


@CIProviderRegistry.register(CIProvider.CIRCLECI)
class CircleCIProvider(CIProviderInterface):
    """CircleCI provider."""

    @property
    def provider_type(self) -> CIProvider:
        return CIProvider.CIRCLECI

    @property
    def name(self) -> str:
        return "CircleCI"

    def _validate_config(self) -> None:
        if not self.config.token:
            logger.warning("CircleCI token not provided - API access may be limited")

    def wait_rate_limit(self) -> None:
        """Wait for CircleCI API rate limit."""
        import time

        # CircleCI rate limit: ~300 requests/minute = 5/second
        # Simple sleep-based throttle (no cross-worker coordination needed)
        time.sleep(0.2)  # 5 req/sec

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["Circle-Token"] = self.config.token
        return headers

    def _get_base_url(self) -> str:
        return self.config.base_url or CIRCLECI_API_BASE

    def _get_project_slug(self, repo_name: str) -> str:
        if "/" in repo_name and not repo_name.startswith(("gh/", "bb/", "github/", "bitbucket/")):
            return f"gh/{repo_name}"
        return repo_name

    async def fetch_builds(
        self,
        repo_name: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
        page: int = 1,
        branch: Optional[str] = None,
        only_with_logs: bool = False,
        exclude_bots: bool = False,
        only_completed: bool = True,
    ) -> List[BuildData]:
        """Fetch builds from CircleCI (single page)."""
        base_url = self._get_base_url()
        project_slug = self._get_project_slug(repo_name)
        url = f"{base_url}/project/{project_slug}/pipeline"

        # CircleCI doesn't support page number, but we can skip to page N
        # by making N-1 requests first (not ideal but works)
        # For simplicity, we'll just fetch one page at a time
        params = {}
        if branch:
            params["branch"] = branch

        builds = []
        consecutive_unavailable = 0
        async with httpx.AsyncClient() as client:
            # Skip to the desired page by following page tokens
            current_page = 1
            next_page_token = None

            while current_page <= page:
                if next_page_token:
                    params["page-token"] = next_page_token

                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                next_page_token = data.get("next_page_token")

                # If we're at the target page, process items
                if current_page == page:
                    if not items:
                        break

                    for pipeline in items:
                        build_data = await self._parse_pipeline(client, pipeline, repo_name)

                        if only_completed and build_data.status in [
                            BuildStatus.PENDING.value,
                            BuildStatus.RUNNING.value,
                            "pending",
                            "running",
                        ]:
                            continue

                        is_bot = _is_bot_author(build_data.commit_author)
                        build_data.is_bot_commit = is_bot

                        if exclude_bots and is_bot:
                            continue

                        if since and build_data.created_at and build_data.created_at < since:
                            continue

                        if only_with_logs:
                            logs_available = await self._check_logs_available(
                                client, pipeline["id"]
                            )
                            build_data.logs_available = logs_available
                            if not logs_available:
                                consecutive_unavailable += 1
                                if consecutive_unavailable >= settings.LOG_UNAVAILABLE_THRESHOLD:
                                    logger.warning(
                                        f"Reached {consecutive_unavailable} consecutive unavailable logs "
                                        f"for {repo_name} - may be permission issue, stopping fetch"
                                    )
                                    break
                                continue
                            else:
                                consecutive_unavailable = 0

                        builds.append(build_data)

                        if limit is not None and len(builds) >= limit:
                            break

                    break  # Exit after processing target page

                current_page += 1
                if not next_page_token:
                    break  # No more pages

        return builds[:limit] if limit else builds

    async def _check_logs_available(self, client: httpx.AsyncClient, pipeline_id: str) -> bool:
        """Check if logs are still available for a pipeline."""
        base_url = self._get_base_url()
        # Get workflows for pipeline
        workflow_url = f"{base_url}/pipeline/{pipeline_id}/workflow"
        try:
            response = await client.get(
                workflow_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            if response.status_code != 200:
                return False
            workflows = response.json().get("items", [])
            if not workflows:
                return False
            # Check first workflow's jobs
            workflow_id = workflows[0]["id"]
            jobs_url = f"{base_url}/workflow/{workflow_id}/job"
            jobs_response = await client.get(
                jobs_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            if jobs_response.status_code != 200:
                return False
            jobs = jobs_response.json().get("items", [])
            return len(jobs) > 0  # If jobs exist, logs should be available
        except Exception as e:
            logger.warning(f"Failed to check logs for pipeline {pipeline_id}: {e}")
            return False

    async def fetch_build_details(self, build_id: str) -> Optional[BuildData]:
        """Fetch details for a specific pipeline."""
        # Handle repo_name:build_id format (extract just the build_id)
        if ":" in build_id:
            _, build_id = build_id.rsplit(":", 1)

        base_url = self._get_base_url()
        url = f"{base_url}/pipeline/{build_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                timeout=30.0,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            pipeline = response.json()

            # Get project slug from pipeline
            project_slug = pipeline.get("project_slug", "")
            repo_name = project_slug.replace("gh/", "").replace("bb/", "")

            return await self._parse_pipeline(client, pipeline, repo_name)

    async def fetch_build_jobs(self, build_id: str) -> List[JobData]:
        """Fetch jobs for a pipeline."""
        base_url = self._get_base_url()

        # First, get workflows for pipeline
        url = f"{base_url}/pipeline/{build_id}/workflow"

        jobs = []
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                timeout=30.0,
            )
            if response.status_code != 200:
                return []

            workflows = response.json().get("items", [])

            # Get jobs for each workflow
            for workflow in workflows:
                workflow_id = workflow.get("id")
                jobs_url = f"{base_url}/workflow/{workflow_id}/job"

                jobs_response = await client.get(
                    jobs_url,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                if jobs_response.status_code == 200:
                    for job in jobs_response.json().get("items", []):
                        jobs.append(self._parse_job(job))

        return jobs

    async def fetch_build_logs(
        self,
        build_id: str,
        job_id: Optional[str] = None,
    ) -> List[LogFile]:
        """Fetch logs for jobs in a pipeline."""
        logs = []

        async with httpx.AsyncClient() as client:
            if job_id:
                # Fetch specific job's steps/output
                log = await self._fetch_job_log(client, job_id)
                if log:
                    logs.append(log)
            else:
                # Fetch all jobs' logs
                jobs = await self.fetch_build_jobs(build_id)
                for job in jobs:
                    try:
                        log = await self._fetch_job_log(client, job.job_id)
                        if log:
                            log.job_name = job.job_name
                            logs.append(log)
                    except Exception as e:
                        logger.warning(f"Failed to fetch log for job {job.job_id}: {e}")

        return logs

    async def _fetch_job_log(self, client: httpx.AsyncClient, job_id: str) -> Optional[LogFile]:
        """Fetch log content for a specific job."""
        base_url = self._get_base_url()

        # Get job details first
        job_url = f"{base_url}/project/job/{job_id}"
        response = await client.get(
            job_url,
            headers=self._get_headers(),
            timeout=30.0,
        )

        if response.status_code != 200:
            return None

        job = response.json()

        # Collect output from all steps
        log_content = []
        for step in job.get("steps", []):
            for action in step.get("actions", []):
                output_url = action.get("output_url")
                if output_url:
                    try:
                        output_response = await client.get(output_url, timeout=60.0)
                        if output_response.status_code == 200:
                            log_content.append(output_response.text)
                    except Exception:
                        pass

        content = "\n".join(log_content)
        return LogFile(
            job_id=job_id,
            job_name=job.get("name", "job"),
            path=f"job_{job_id}.log",
            content=content,
            size_bytes=len(content.encode()),
        )

    def normalize_status(self, raw_status: str) -> BuildStatus:
        """Normalize CircleCI status to BuildStatus enum."""
        status_map = {
            "pending": BuildStatus.PENDING,
            "queued": BuildStatus.QUEUED,
            "running": BuildStatus.RUNNING,
            "on_hold": BuildStatus.PENDING,
            # Completed states
            "success": BuildStatus.COMPLETED,
            "failed": BuildStatus.COMPLETED,
            "error": BuildStatus.COMPLETED,
            "canceled": BuildStatus.COMPLETED,
            "not_run": BuildStatus.COMPLETED,
        }
        return status_map.get(raw_status.lower(), BuildStatus.UNKNOWN)

    def normalize_conclusion(self, raw_status: str) -> BuildConclusion:
        """Normalize CircleCI status to BuildConclusion enum."""
        conclusion_map = {
            "success": BuildConclusion.SUCCESS,
            "failed": BuildConclusion.FAILURE,
            "error": BuildConclusion.FAILURE,
            "canceled": BuildConclusion.CANCELLED,
            "not_run": BuildConclusion.SKIPPED,
            "timedout": BuildConclusion.TIMED_OUT,
        }
        return (
            conclusion_map.get(raw_status.lower(), BuildConclusion.NONE)
            if raw_status
            else BuildConclusion.NONE
        )

    async def _parse_pipeline(
        self, client: httpx.AsyncClient, pipeline: dict, repo_name: str
    ) -> BuildData:
        """Parse CircleCI pipeline to BuildData."""
        # Parse timestamps
        created_at = None
        started_at = None
        stopped_at = None
        if pipeline.get("created_at"):
            created_at = datetime.fromisoformat(pipeline["created_at"].replace("Z", "+00:00"))

        # Get overall status from workflows
        base_url = self._get_base_url()
        status = "pending"

        try:
            workflow_url = f"{base_url}/pipeline/{pipeline['id']}/workflow"
            response = await client.get(
                workflow_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            if response.status_code == 200:
                workflows = response.json().get("items", [])
                if workflows:
                    status = workflows[0].get("status", "unknown")
                    if workflows[0].get("started_at"):
                        started_at = datetime.fromisoformat(
                            workflows[0]["started_at"].replace("Z", "+00:00")
                        )
                    if workflows[0].get("stopped_at"):
                        stopped_at = datetime.fromisoformat(
                            workflows[0]["stopped_at"].replace("Z", "+00:00")
                        )
        except Exception:
            pass

        # Calculate duration
        duration_seconds = None
        if started_at and stopped_at:
            duration_seconds = (stopped_at - started_at).total_seconds()

        # Get commit info
        vcs = pipeline.get("vcs", {})

        # Build web URL
        project_slug = pipeline.get("project_slug", "")
        pipeline_number = pipeline.get("number", "")
        web_url = (
            f"https://app.circleci.com/pipelines/{project_slug}/{pipeline_number}"
            if project_slug
            else None
        )

        return BuildData(
            build_id=pipeline.get("id"),
            build_number=pipeline.get("number"),
            repo_name=repo_name,
            branch=vcs.get("branch"),
            commit_sha=vcs.get("revision"),
            commit_message=(vcs.get("commit", {}).get("subject") if vcs.get("commit") else None),
            commit_author=(
                vcs.get("commit", {}).get("author", {}).get("name") if vcs.get("commit") else None
            ),
            status=self.normalize_status(status),
            conclusion=self.normalize_conclusion(status),
            created_at=created_at,
            started_at=started_at,
            completed_at=stopped_at,
            duration_seconds=duration_seconds,
            web_url=web_url,
            provider=CIProvider.CIRCLECI,
            raw_data=pipeline,
        )

    def _parse_job(self, job: dict) -> JobData:
        """Parse CircleCI job to JobData."""
        started_at = None
        if job.get("started_at"):
            started_at = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))

        stopped_at = None
        if job.get("stopped_at"):
            stopped_at = datetime.fromisoformat(job["stopped_at"].replace("Z", "+00:00"))

        duration = None
        if started_at and stopped_at:
            duration = (stopped_at - started_at).total_seconds()

        return JobData(
            job_id=str(job.get("id")),
            job_name=job.get("name", "unknown"),
            status=self.normalize_status(job.get("status", "unknown")),
            started_at=started_at,
            completed_at=stopped_at,
            duration_seconds=duration,
        )

    def get_repo_url(self, repo_name: str) -> str:
        return f"https://github.com/{repo_name}"

    def get_build_url(self, repo_name: str, build_id: str) -> str:
        project_slug = self._get_project_slug(repo_name)
        return f"https://app.circleci.com/pipelines/{project_slug}/{build_id}"
