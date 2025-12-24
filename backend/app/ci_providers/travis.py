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

TRAVIS_API_BASE = "https://api.travis-ci.com"

BOT_PATTERNS = ["[bot]", "dependabot", "renovate", "travis", "github-actions"]


def _is_bot_author(author: Optional[str]) -> bool:
    if not author:
        return False
    return any(pattern in author.lower() for pattern in BOT_PATTERNS)


@CIProviderRegistry.register(CIProvider.TRAVIS_CI)
class TravisCIProvider(CIProviderInterface):
    """
    Travis CI provider.

    Fetches builds, jobs, and logs from Travis CI API.

    Config:
        token: Travis CI API token
        base_url: Optional custom API URL (travis-ci.com or travis-ci.org)
    """

    @property
    def provider_type(self) -> CIProvider:
        return CIProvider.TRAVIS_CI

    @property
    def name(self) -> str:
        return "Travis CI"

    def _validate_config(self) -> None:
        if not self.config.token:
            logger.warning("Travis CI token not provided - API access may be limited")

    def wait_rate_limit(self) -> None:
        """Wait for Travis CI API rate limit."""
        import time

        # Travis CI has generous rate limits but still throttle to be safe
        time.sleep(0.1)  # ~10 req/sec

    def _get_headers(self) -> dict:
        """Get HTTP headers for Travis CI API requests."""
        headers = {
            "Travis-API-Version": "3",
            "Content-Type": "application/json",
        }
        if self.config.token:
            headers["Authorization"] = f"token {self.config.token}"
        return headers

    def _get_base_url(self) -> str:
        """Get API base URL."""
        return self.config.base_url or TRAVIS_API_BASE

    def _encode_repo_slug(self, repo_name: str) -> str:
        """URL-encode repo slug for Travis CI API."""
        import urllib.parse

        return urllib.parse.quote(repo_name, safe="")

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
        """Fetch builds from Travis CI (single page)."""
        base_url = self._get_base_url()
        repo_slug = self._encode_repo_slug(repo_name)
        url = f"{base_url}/repo/{repo_slug}/builds"

        per_page = min(limit or 100, 100)
        # Calculate offset from page number (1-indexed)
        offset = (page - 1) * per_page

        params = {
            "limit": per_page,
            "offset": offset,
            "sort_by": "started_at:desc",
        }
        if branch:
            params["branch.name"] = branch
        if only_completed:
            params["state"] = "passed,failed,errored,canceled"

        builds = []
        consecutive_unavailable = 0
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            build_list = data.get("builds", [])

            for build in build_list:
                build_data = self._parse_build(build, repo_name)

                is_bot = _is_bot_author(build_data.commit_author)
                build_data.is_bot_commit = is_bot

                if exclude_bots and is_bot:
                    continue

                if since and build_data.created_at and build_data.created_at < since:
                    continue

                if only_with_logs:
                    logs_available = await self._check_logs_available(client, build["id"])
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

        return builds[:limit] if limit else builds

    async def _check_logs_available(self, client: httpx.AsyncClient, build_id: int) -> bool:
        """Check if logs are still available for a build."""
        base_url = self._get_base_url()
        jobs_url = f"{base_url}/build/{build_id}/jobs"
        try:
            response = await client.get(
                jobs_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            if response.status_code != 200:
                return False
            jobs = response.json().get("jobs", [])
            if not jobs:
                return False
            # Check first job's log
            first_job = jobs[0]
            log_url = f"{base_url}/job/{first_job['id']}/log"
            headers = self._get_headers()
            headers["Accept"] = "text/plain"
            log_response = await client.head(
                log_url,
                headers=headers,
                timeout=10.0,
            )
            return log_response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to check logs for build {build_id}: {e}")
            return False

    async def fetch_build_details(self, build_id: str) -> Optional[BuildData]:
        """Fetch details for a specific build."""
        if ":" in build_id:
            _, build_id = build_id.rsplit(":", 1)

        base_url = self._get_base_url()
        url = f"{base_url}/build/{build_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                timeout=30.0,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            build = response.json()

            # Get repo name from build
            repo = build.get("repository", {})
            repo_name = repo.get("slug", "")

            return self._parse_build(build, repo_name)

    async def fetch_build_jobs(self, build_id: str) -> List[JobData]:
        """Fetch jobs for a build."""
        base_url = self._get_base_url()
        url = f"{base_url}/build/{build_id}/jobs"

        jobs = []
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                timeout=30.0,
            )
            if response.status_code != 200:
                return []

            for job in response.json().get("jobs", []):
                jobs.append(self._parse_job(job))

        return jobs

    async def fetch_build_logs(
        self,
        build_id: str,
        job_id: Optional[str] = None,
    ) -> List[LogFile]:
        """Fetch logs for a build's jobs."""
        base_url = self._get_base_url()
        logs = []

        async with httpx.AsyncClient() as client:
            if job_id:
                # Fetch specific job log
                log = await self._fetch_job_log(client, base_url, job_id)
                if log:
                    logs.append(log)
            else:
                # Fetch all jobs' logs
                jobs = await self.fetch_build_jobs(build_id)
                for job in jobs:
                    try:
                        log = await self._fetch_job_log(client, base_url, job.job_id)
                        if log:
                            log.job_name = job.job_name
                            logs.append(log)
                    except Exception as e:
                        logger.warning(f"Failed to fetch log for job {job.job_id}: {e}")

        return logs

    async def _fetch_job_log(
        self, client: httpx.AsyncClient, base_url: str, job_id: str
    ) -> Optional[LogFile]:
        """Fetch log content for a specific job."""
        url = f"{base_url}/job/{job_id}/log"

        # Request plain text log
        headers = self._get_headers()
        headers["Accept"] = "text/plain"

        response = await client.get(
            url,
            headers=headers,
            timeout=60.0,
        )

        if response.status_code != 200:
            return None

        content = response.text
        return LogFile(
            job_id=job_id,
            job_name="job",
            path=f"job_{job_id}.log",
            content=content,
            size_bytes=len(content.encode()),
        )

    def normalize_status(self, raw_state: str) -> BuildStatus:
        """Normalize Travis CI state to BuildStatus enum."""
        status_map = {
            "created": BuildStatus.PENDING,
            "queued": BuildStatus.QUEUED,
            "received": BuildStatus.PENDING,
            "started": BuildStatus.RUNNING,
            # Completed states
            "passed": BuildStatus.COMPLETED,
            "failed": BuildStatus.COMPLETED,
            "errored": BuildStatus.COMPLETED,
            "canceled": BuildStatus.COMPLETED,
        }
        return status_map.get(raw_state.lower(), BuildStatus.UNKNOWN)

    def normalize_conclusion(self, raw_state: str) -> BuildConclusion:
        """Normalize Travis CI state to BuildConclusion enum."""
        conclusion_map = {
            "passed": BuildConclusion.SUCCESS,
            "failed": BuildConclusion.FAILURE,
            "errored": BuildConclusion.FAILURE,
            "canceled": BuildConclusion.CANCELLED,
        }
        return (
            conclusion_map.get(raw_state.lower(), BuildConclusion.NONE)
            if raw_state
            else BuildConclusion.NONE
        )

    def _parse_build(self, build: dict, repo_name: str) -> BuildData:
        """Parse Travis CI build to BuildData."""
        # Parse timestamps
        created_at = None
        if build.get("started_at"):
            created_at = datetime.fromisoformat(build["started_at"].replace("Z", "+00:00"))

        finished_at = None
        if build.get("finished_at"):
            finished_at = datetime.fromisoformat(build["finished_at"].replace("Z", "+00:00"))

        # Duration
        duration = build.get("duration")

        # Get commit info
        commit = build.get("commit", {})

        return BuildData(
            build_id=str(build.get("id")),
            build_number=build.get("number"),
            repo_name=repo_name,
            branch=build.get("branch", {}).get("name") if build.get("branch") else None,
            commit_sha=commit.get("sha"),
            commit_message=commit.get("message"),
            commit_author=(commit.get("author", {}).get("name") if commit.get("author") else None),
            status=self.normalize_status(build.get("state", "unknown")),
            conclusion=self.normalize_conclusion(build.get("state")),
            created_at=created_at,
            started_at=created_at,
            completed_at=finished_at,
            duration_seconds=float(duration) if duration else None,
            web_url=f"https://app.travis-ci.com/{repo_name}/builds/{build.get('id')}",
            provider=CIProvider.TRAVIS_CI,
            raw_data=build,
        )

    def _parse_job(self, job: dict) -> JobData:
        """Parse Travis CI job to JobData."""
        started_at = None
        if job.get("started_at"):
            started_at = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))

        finished_at = None
        if job.get("finished_at"):
            finished_at = datetime.fromisoformat(job["finished_at"].replace("Z", "+00:00"))

        duration = None
        if started_at and finished_at:
            duration = (finished_at - started_at).total_seconds()

        # Job name from config or number
        job_name = f"Job {job.get('number', job.get('id'))}"
        if job.get("config"):
            config = job["config"]
            if isinstance(config, dict):
                # Try to create meaningful name from config
                parts = []
                if config.get("os"):
                    parts.append(config["os"])
                if config.get("language"):
                    parts.append(config["language"])
                if parts:
                    job_name = " - ".join(parts)

        return JobData(
            job_id=str(job.get("id")),
            job_name=job_name,
            status=self.normalize_status(job.get("state", "unknown")),
            started_at=started_at,
            completed_at=finished_at,
            duration_seconds=duration,
        )

    def get_repo_url(self, repo_name: str) -> str:
        return f"https://github.com/{repo_name}"

    def get_build_url(self, repo_name: str, build_id: str) -> str:
        return f"https://app.travis-ci.com/{repo_name}/builds/{build_id}"
