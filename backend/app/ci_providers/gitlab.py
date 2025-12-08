import logging
from datetime import datetime
from typing import List, Optional

import httpx

from .base import CIProviderInterface
from .factory import CIProviderRegistry
from .models import (
    BuildData,
    BuildStatus,
    CIProvider,
    JobData,
    LogFile,
    ProviderConfig,
)

logger = logging.getLogger(__name__)

GITLAB_API_BASE = "https://gitlab.com/api/v4"

BOT_PATTERNS = [
    "[bot]",
    "dependabot",
    "renovate",
    "gitlab-bot",
    "semantic-release",
    "greenkeeper",
    "snyk-bot",
    "codecov",
]


def _is_bot_author(author: Optional[str]) -> bool:
    if not author:
        return False
    author_lower = author.lower()
    return any(pattern in author_lower for pattern in BOT_PATTERNS)


@CIProviderRegistry.register(CIProvider.GITLAB_CI)
class GitLabCIProvider(CIProviderInterface):
    @property
    def provider_type(self) -> CIProvider:
        return CIProvider.GITLAB_CI

    @property
    def name(self) -> str:
        return "GitLab CI"

    def _validate_config(self) -> None:
        if not self.config.token:
            logger.warning("GitLab token not provided - API access may be limited")

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.config.token:
            headers["PRIVATE-TOKEN"] = self.config.token
        return headers

    def _get_base_url(self) -> str:
        return self.config.base_url or GITLAB_API_BASE

    def _encode_project_path(self, repo_name: str) -> str:
        import urllib.parse

        return urllib.parse.quote(repo_name, safe="")

    async def fetch_builds(
        self,
        repo_name: str,
        since: Optional[datetime] = None,
        limit: Optional[int] = None,
        branch: Optional[str] = None,
        only_with_logs: bool = False,
        exclude_bots: bool = False,
    ) -> List[BuildData]:
        base_url = self._get_base_url()
        project_path = self._encode_project_path(repo_name)
        url = f"{base_url}/projects/{project_path}/pipelines"

        per_page = 100 if limit is None else min(limit, 100)
        params = {"per_page": per_page}
        if branch:
            params["ref"] = branch
        if since:
            params["updated_after"] = since.isoformat()

        builds = []
        stop_fetching = False
        async with httpx.AsyncClient() as client:
            page = 1
            while not stop_fetching:
                params["page"] = page
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                pipelines = response.json()

                if not pipelines:
                    break

                for pipeline in pipelines:
                    build_data = self._parse_pipeline(pipeline, repo_name)

                    # Check if this is a bot commit
                    is_bot = _is_bot_author(build_data.commit_author)
                    build_data.is_bot_commit = is_bot

                    if exclude_bots and is_bot:
                        logger.debug(f"Skipping bot commit: {build_data.commit_author}")
                        continue

                    if only_with_logs:
                        logs_available = await self._check_logs_available(
                            client, project_path, pipeline["id"]
                        )
                        build_data.logs_available = logs_available
                        if not logs_available:
                            logger.info(
                                f"Pipeline {pipeline['id']} has no logs available, stopping fetch"
                            )
                            stop_fetching = True
                            break

                    builds.append(build_data)

                if limit is not None and len(builds) >= limit:
                    break

                if len(pipelines) < per_page:
                    break

                page += 1

        return builds[:limit] if limit else builds

    async def _check_logs_available(
        self, client: httpx.AsyncClient, project_path: str, pipeline_id: int
    ) -> bool:
        """Check if logs are still available for a pipeline."""
        base_url = self._get_base_url()
        jobs_url = f"{base_url}/projects/{project_path}/pipelines/{pipeline_id}/jobs"
        try:
            response = await client.get(
                jobs_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            if response.status_code != 200:
                return False
            jobs = response.json()
            if not jobs:
                return False
            # Check first job's trace (log)
            first_job = jobs[0]
            trace_url = (
                f"{base_url}/projects/{project_path}/jobs/{first_job['id']}/trace"
            )
            trace_response = await client.head(
                trace_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            return trace_response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to check logs for pipeline {pipeline_id}: {e}")
            return False

    async def fetch_build_details(self, build_id: str) -> Optional[BuildData]:
        # build_id format: "project/path:pipeline_id"
        if ":" in build_id:
            repo_name, pipeline_id = build_id.rsplit(":", 1)
        else:
            return None

        base_url = self._get_base_url()
        project_path = self._encode_project_path(repo_name)
        url = f"{base_url}/projects/{project_path}/pipelines/{pipeline_id}"

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
            return self._parse_pipeline(pipeline, repo_name)

    async def fetch_build_jobs(self, build_id: str) -> List[JobData]:
        if ":" in build_id:
            repo_name, pipeline_id = build_id.rsplit(":", 1)
        else:
            return []

        base_url = self._get_base_url()
        project_path = self._encode_project_path(repo_name)
        url = f"{base_url}/projects/{project_path}/pipelines/{pipeline_id}/jobs"

        jobs = []
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                timeout=30.0,
            )
            response.raise_for_status()
            job_list = response.json()

            for job in job_list:
                jobs.append(self._parse_job(job))

        return jobs

    async def fetch_build_logs(
        self,
        build_id: str,
        job_id: Optional[str] = None,
    ) -> List[LogFile]:
        if ":" in build_id:
            repo_name, pipeline_id = build_id.rsplit(":", 1)
        else:
            return []

        base_url = self._get_base_url()
        project_path = self._encode_project_path(repo_name)
        logs = []

        async with httpx.AsyncClient() as client:
            if job_id:
                # Fetch specific job log
                url = f"{base_url}/projects/{project_path}/jobs/{job_id}/trace"
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=60.0,
                )
                if response.status_code == 200:
                    logs.append(
                        LogFile(
                            job_id=job_id,
                            job_name="job",
                            path=f"job_{job_id}.log",
                            content=response.text,
                            size_bytes=len(response.content),
                        )
                    )
            else:
                # Fetch all jobs' logs
                jobs = await self.fetch_build_jobs(build_id)
                for job in jobs:
                    url = f"{base_url}/projects/{project_path}/jobs/{job.job_id}/trace"
                    try:
                        response = await client.get(
                            url,
                            headers=self._get_headers(),
                            timeout=60.0,
                        )
                        if response.status_code == 200:
                            logs.append(
                                LogFile(
                                    job_id=job.job_id,
                                    job_name=job.job_name,
                                    path=f"{job.job_name}.log",
                                    content=response.text,
                                    size_bytes=len(response.content),
                                )
                            )
                    except Exception as e:
                        logger.warning(f"Failed to fetch log for job {job.job_id}: {e}")

        return logs

    def normalize_status(self, raw_status: str) -> str:
        status_map = {
            "created": BuildStatus.PENDING,
            "waiting_for_resource": BuildStatus.PENDING,
            "preparing": BuildStatus.PENDING,
            "pending": BuildStatus.PENDING,
            "running": BuildStatus.RUNNING,
            "success": BuildStatus.SUCCESS,
            "failed": BuildStatus.FAILURE,
            "canceled": BuildStatus.CANCELLED,
            "skipped": BuildStatus.SKIPPED,
            "manual": BuildStatus.PENDING,
            "scheduled": BuildStatus.PENDING,
        }
        return status_map.get(raw_status.lower(), BuildStatus.UNKNOWN).value

    def _parse_pipeline(self, pipeline: dict, repo_name: str) -> BuildData:
        created_at = None
        if pipeline.get("created_at"):
            created_at = datetime.fromisoformat(
                pipeline["created_at"].replace("Z", "+00:00")
            )

        started_at = None
        if pipeline.get("started_at"):
            started_at = datetime.fromisoformat(
                pipeline["started_at"].replace("Z", "+00:00")
            )

        completed_at = None
        if pipeline.get("finished_at"):
            completed_at = datetime.fromisoformat(
                pipeline["finished_at"].replace("Z", "+00:00")
            )

        duration = pipeline.get("duration")

        return BuildData(
            build_id=str(pipeline["id"]),
            build_number=pipeline.get("iid"),
            repo_name=repo_name,
            branch=pipeline.get("ref"),
            commit_sha=pipeline.get("sha"),
            status=self.normalize_status(pipeline.get("status", "unknown")),
            conclusion=pipeline.get("status"),
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=float(duration) if duration else None,
            web_url=pipeline.get("web_url"),
            provider=CIProvider.GITLAB_CI,
            raw_data=pipeline,
        )

    def _parse_job(self, job: dict) -> JobData:
        started_at = None
        if job.get("started_at"):
            started_at = datetime.fromisoformat(
                job["started_at"].replace("Z", "+00:00")
            )

        completed_at = None
        if job.get("finished_at"):
            completed_at = datetime.fromisoformat(
                job["finished_at"].replace("Z", "+00:00")
            )

        duration = job.get("duration")

        return JobData(
            job_id=str(job["id"]),
            job_name=job.get("name", "unknown"),
            status=self.normalize_status(job.get("status", "unknown")),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=float(duration) if duration else None,
        )

    def get_repo_url(self, repo_name: str) -> str:
        base = self.config.base_url or "https://gitlab.com"
        base = base.replace("/api/v4", "")
        return f"{base}/{repo_name}"

    def get_build_url(self, repo_name: str, build_id: str) -> str:
        base = self.config.base_url or "https://gitlab.com"
        base = base.replace("/api/v4", "")
        return f"{base}/{repo_name}/-/pipelines/{build_id}"
