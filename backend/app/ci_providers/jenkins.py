import logging
from datetime import datetime, timezone
from typing import List, Optional
from base64 import b64encode

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

BOT_PATTERNS = ["[bot]", "dependabot", "renovate", "jenkins", "github-actions"]


def _is_bot_author(author: Optional[str]) -> bool:
    if not author:
        return False
    return any(pattern in author.lower() for pattern in BOT_PATTERNS)


@CIProviderRegistry.register(CIProvider.JENKINS)
class JenkinsProvider(CIProviderInterface):
    @property
    def provider_type(self) -> CIProvider:
        return CIProvider.JENKINS

    @property
    def name(self) -> str:
        return "Jenkins"

    def _validate_config(self) -> None:
        if not self.config.base_url:
            raise ValueError("Jenkins base_url is required")

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}

        if self.config.username and self.config.token:
            credentials = f"{self.config.username}:{self.config.token}"
            encoded = b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

        return headers

    def _get_base_url(self) -> str:
        url = self.config.base_url or ""
        return url.rstrip("/")

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
        job_path = repo_name.replace("/", "/job/")
        url = f"{base_url}/job/{job_path}/api/json"

        params = {
            "tree": "builds[number,url,result,timestamp,duration,building,actions[lastBuiltRevision[SHA1,branch[name]]]]",
        }

        builds = []
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            all_builds = data.get("builds", [])
            if limit is not None:
                all_builds = all_builds[:limit]

            for build in all_builds:
                build_data = self._parse_build(build, repo_name)

                is_bot = _is_bot_author(build_data.commit_author)
                build_data.is_bot_commit = is_bot

                if exclude_bots and is_bot:
                    continue

                if since and build_data.created_at and build_data.created_at < since:
                    continue

                if only_with_logs:
                    logs_available = await self._check_logs_available(
                        client, job_path, build["number"]
                    )
                    build_data.logs_available = logs_available
                    if not logs_available:
                        logger.info(
                            f"Build {build['number']} has no logs available, stopping fetch"
                        )
                        break

                builds.append(build_data)

        return builds[:limit] if limit else builds

    async def _check_logs_available(
        self, client: httpx.AsyncClient, job_path: str, build_number: int
    ) -> bool:
        """Check if logs are still available for a build."""
        base_url = self._get_base_url()
        log_url = f"{base_url}/job/{job_path}/{build_number}/consoleText"
        try:
            response = await client.head(
                log_url,
                headers=self._get_headers(),
                timeout=10.0,
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to check logs for build {build_number}: {e}")
            return False

    async def fetch_build_details(self, build_id: str) -> Optional[BuildData]:
        # build_id format: "job/path:build_number"
        if ":" in build_id:
            job_name, build_number = build_id.rsplit(":", 1)
        else:
            return None

        base_url = self._get_base_url()
        job_path = job_name.replace("/", "/job/")
        url = f"{base_url}/job/{job_path}/{build_number}/api/json"

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
            return self._parse_build(build, job_name)

    async def fetch_build_jobs(self, build_id: str) -> List[JobData]:
        if ":" in build_id:
            job_name, build_number = build_id.rsplit(":", 1)
        else:
            return []

        base_url = self._get_base_url()
        job_path = job_name.replace("/", "/job/")

        # Try Pipeline stages API (Blue Ocean)
        url = f"{base_url}/blue/rest/organizations/jenkins/pipelines/{job_path}/runs/{build_number}/nodes/"

        jobs = []
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=30.0,
                )
                if response.status_code == 200:
                    nodes = response.json()
                    for node in nodes:
                        jobs.append(self._parse_stage(node))
            except Exception as e:
                logger.debug(f"Pipeline stages API not available: {e}")
                # Fallback: return single job representing the whole build
                jobs.append(
                    JobData(
                        job_id=build_number,
                        job_name=job_name,
                        status=BuildStatus.UNKNOWN,
                    )
                )

        return jobs

    async def fetch_build_logs(
        self,
        build_id: str,
        job_id: Optional[str] = None,
    ) -> List[LogFile]:
        if ":" in build_id:
            job_name, build_number = build_id.rsplit(":", 1)
        else:
            return []

        base_url = self._get_base_url()
        job_path = job_name.replace("/", "/job/")
        url = f"{base_url}/job/{job_path}/{build_number}/consoleText"

        logs = []
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self._get_headers(),
                timeout=60.0,
            )
            if response.status_code == 200:
                logs.append(
                    LogFile(
                        job_id=build_number,
                        job_name=job_name,
                        path=f"build_{build_number}.log",
                        content=response.text,
                        size_bytes=len(response.content),
                    )
                )

        return logs

    def normalize_status(self, raw_status: str) -> str:
        if raw_status is None:
            return BuildStatus.RUNNING.value

        status_map = {
            "success": BuildStatus.SUCCESS,
            "failure": BuildStatus.FAILURE,
            "unstable": BuildStatus.FAILURE,
            "aborted": BuildStatus.CANCELLED,
            "not_built": BuildStatus.SKIPPED,
        }
        return status_map.get(raw_status.lower(), BuildStatus.UNKNOWN).value

    def _parse_build(self, build: dict, job_name: str) -> BuildData:
        timestamp = build.get("timestamp")
        created_at = None
        if timestamp:
            created_at = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)

        duration = build.get("duration")
        duration_seconds = duration / 1000 if duration else None

        commit_sha = None
        branch = None
        for action in build.get("actions", []):
            if "lastBuiltRevision" in action:
                revision = action["lastBuiltRevision"]
                commit_sha = revision.get("SHA1")
                branches = revision.get("branch", [])
                if branches:
                    branch = (
                        branches[0].get("name", "").replace("refs/remotes/origin/", "")
                    )

        result = build.get("result")
        if build.get("building"):
            status = BuildStatus.RUNNING.value
        else:
            status = self.normalize_status(result)

        return BuildData(
            build_id=str(build.get("number")),
            build_number=build.get("number"),
            repo_name=job_name,
            branch=branch,
            commit_sha=commit_sha,
            status=status,
            conclusion=result,
            created_at=created_at,
            started_at=created_at,
            completed_at=None,
            duration_seconds=duration_seconds,
            web_url=build.get("url"),
            provider=CIProvider.JENKINS,
            raw_data=build,
        )

    def _parse_stage(self, node: dict) -> JobData:
        """Parse Jenkins Pipeline stage to JobData."""
        started_at = None
        if node.get("startTime"):
            started_at = datetime.fromisoformat(
                node["startTime"].replace("Z", "+00:00")
            )

        duration = node.get("durationInMillis")

        return JobData(
            job_id=str(node.get("id")),
            job_name=node.get("displayName", "unknown"),
            status=self.normalize_status(node.get("result")),
            started_at=started_at,
            duration_seconds=duration / 1000 if duration else None,
        )

    def get_repo_url(self, repo_name: str) -> str:
        base = self._get_base_url()
        job_path = repo_name.replace("/", "/job/")
        return f"{base}/job/{job_path}"

    def get_build_url(self, repo_name: str, build_id: str) -> str:
        base = self._get_base_url()
        job_path = repo_name.replace("/", "/job/")
        return f"{base}/job/{job_path}/{build_id}"
