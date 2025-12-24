"""
GitHub Actions CI Provider - Uses GitHubClient for rate limit tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from pymongo.database import Database

from app.ci_providers.models import BuildConclusion
from app.config import settings

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

# Common bot patterns for filtering
BOT_PATTERNS = [
    "[bot]",
    "dependabot",
    "renovate",
    "github-actions",
    "semantic-release",
    "greenkeeper",
    "snyk-bot",
    "codecov",
    "imgbot",
    "allcontributors",
    "mergify",
    "pre-commit-ci",
]


def _is_bot_author(author: Optional[str]) -> bool:
    """Check if the commit author is likely a bot."""
    if not author:
        return False
    author_lower = author.lower()
    return any(pattern in author_lower for pattern in BOT_PATTERNS)


@CIProviderRegistry.register(CIProvider.GITHUB_ACTIONS)
class GitHubActionsProvider(CIProviderInterface):
    """
    GitHub Actions provider using GitHubClient for automatic token
    rotation and rate limit tracking.
    """

    def __init__(self, config: ProviderConfig, db: Database = None):
        from app.database.mongo import get_database

        self._db = db if db is not None else get_database()
        super().__init__(config)

    @property
    def provider_type(self) -> CIProvider:
        return CIProvider.GITHUB_ACTIONS

    @property
    def name(self) -> str:
        return "GitHub Actions"

    def _has_direct_token(self) -> bool:
        """Return True only when a non-empty string token is provided."""
        token = getattr(self.config, "token", None)
        return isinstance(token, str) and token.strip() != ""

    def _validate_config(self) -> None:
        if not self._has_direct_token():
            if self._db is None:
                logger.warning(
                    "GitHub token not provided and no DB for pool - API rate limits will apply"
                )

    def wait_rate_limit(self) -> None:
        """Wait for GitHub API rate limit using Redis-based rate limiter."""
        from app.services.github.rate_limiter import get_rate_limiter

        get_rate_limiter().wait()

    def _get_github_client(
        self, repo_name: Optional[str] = None, installation_id: Optional[str] = None
    ):
        """
        Get GitHubClient for API calls.

        Priority:
        1. GitHub App installation (if repo belongs to org and installation configured)
        2. Direct config token (if configured)
        3. Public token pool (new instance each time to avoid closing singleton)

        Args:
            repo_name: Repository full name (owner/repo) to check org membership
            installation_id: Explicit installation ID override (bypasses org check)
        """
        from app.services.github.github_client import (
            GitHubClient,
            get_app_github_client,
            get_public_github_client,
        )
        from app.services.model_repository_service import is_org_repo

        # If explicit installation_id provided, use it directly
        if installation_id:
            return get_app_github_client(installation_id)

        # Check if repo belongs to org and use installation token
        if repo_name and is_org_repo(repo_name) and settings.GITHUB_INSTALLATION_ID:
            return get_app_github_client(settings.GITHUB_INSTALLATION_ID)

        # If direct token configured, use it
        if self._has_direct_token():
            return GitHubClient(token=self.config.token)

        return get_public_github_client()

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
        installation_id: Optional[str] = None,
    ) -> List[BuildData]:
        """Fetch workflow runs from GitHub Actions (single page)."""
        builds = []
        consecutive_unavailable = 0

        per_page = min(limit or 100, 100)
        params = {"per_page": per_page, "page": page}
        if branch:
            params["branch"] = branch
        if since:
            params["created"] = f">={since.isoformat()}"
        if only_completed:
            params["status"] = "completed"

        with self._get_github_client(repo_name, installation_id) as client:
            # Fetch single page only (no internal pagination)
            response = client.list_workflow_runs(repo_name, params)
            runs = response.get("workflow_runs", [])

            for run in runs:
                build_data = self._parse_workflow_run(run, repo_name)

                is_bot = _is_bot_author(build_data.commit_author)
                build_data.is_bot_commit = is_bot

                if exclude_bots and is_bot:
                    logger.debug(f"Skipping bot commit: {build_data.commit_author}")
                    continue

                if only_with_logs:
                    logs_available = client.logs_available(repo_name, int(run["id"]))
                    build_data.logs_available = logs_available
                    if not logs_available:
                        consecutive_unavailable += 1
                        if consecutive_unavailable >= settings.GIT_LOG_UNAVAILABLE_THRESHOLD:
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

    async def fetch_build_details(
        self, build_id: str, installation_id: Optional[str] = None
    ) -> Optional[BuildData]:
        """Fetch detailed information for a specific workflow run."""
        if ":" in build_id:
            repo_name, run_id = build_id.rsplit(":", 1)
        else:
            return None

        with self._get_github_client(repo_name, installation_id) as client:
            try:
                run = client.get_workflow_run(repo_name, int(run_id))
                return self._parse_workflow_run(run, repo_name)
            except Exception:
                return None

    async def fetch_build_jobs(
        self, build_id: str, installation_id: Optional[str] = None
    ) -> List[JobData]:
        """Fetch jobs within a workflow run."""
        if ":" in build_id:
            repo_name, run_id = build_id.rsplit(":", 1)
        else:
            return []

        with self._get_github_client(repo_name, installation_id) as client:
            jobs_data = client.list_workflow_jobs(repo_name, int(run_id))
            return [self._parse_job(job) for job in jobs_data]

    async def fetch_build_logs(
        self,
        build_id: str,
        job_id: Optional[str] = None,
        installation_id: Optional[str] = None,
    ) -> List[LogFile]:
        """Fetch logs for a workflow run or specific job."""
        from app.services.github.exceptions import GithubLogsUnavailableError

        if ":" in build_id:
            repo_name, _ = build_id.rsplit(":", 1)
        else:
            return []

        logs = []

        with self._get_github_client(repo_name, installation_id) as client:
            if job_id:
                try:
                    content = client.download_job_logs(repo_name, int(job_id))
                    logs.append(
                        LogFile(
                            job_id=job_id,
                            job_name="job",
                            path=f"job_{job_id}.log",
                            content=content.decode("utf-8", errors="replace"),
                            size_bytes=len(content),
                        )
                    )
                except GithubLogsUnavailableError as e:
                    logger.debug(f"Logs unavailable for job {job_id}: {e.reason}")
                except Exception as e:
                    logger.warning(f"Failed to fetch log for job {job_id}: {e}")
            else:
                jobs = await self.fetch_build_jobs(build_id)
                for job in jobs:
                    try:
                        content = client.download_job_logs(repo_name, int(job.job_id))
                        logs.append(
                            LogFile(
                                job_id=job.job_id,
                                job_name=job.job_name,
                                path=f"{job.job_name}.log",
                                content=content.decode("utf-8", errors="replace"),
                                size_bytes=len(content),
                            )
                        )
                    except GithubLogsUnavailableError as e:
                        logger.debug(f"Logs unavailable for job {job.job_id}: {e.reason}")
                    except Exception as e:
                        logger.warning(f"Failed to fetch log for job {job.job_id}: {e}")

        return logs

    def normalize_status(self, raw_status: str) -> BuildStatus:
        """Normalize GitHub Actions status to BuildStatus enum."""
        status_map = {
            "queued": BuildStatus.QUEUED,
            "waiting": BuildStatus.PENDING,
            "pending": BuildStatus.PENDING,
            "in_progress": BuildStatus.RUNNING,
            "completed": BuildStatus.COMPLETED,
        }
        return status_map.get(raw_status.lower(), BuildStatus.UNKNOWN)

    def normalize_conclusion(self, raw_conclusion: str) -> BuildConclusion:
        """Normalize GitHub Actions conclusion to BuildConclusion enum."""
        conclusion_map = {
            "success": BuildConclusion.SUCCESS,
            "failure": BuildConclusion.FAILURE,
            "cancelled": BuildConclusion.CANCELLED,
            "skipped": BuildConclusion.SKIPPED,
            "timed_out": BuildConclusion.TIMED_OUT,
            "action_required": BuildConclusion.ACTION_REQUIRED,
            "neutral": BuildConclusion.NEUTRAL,
            "stale": BuildConclusion.STALE,
        }
        return (
            conclusion_map.get(raw_conclusion.lower(), BuildConclusion.UNKNOWN)
            if raw_conclusion
            else BuildConclusion.NONE
        )

    def _parse_workflow_run(self, run: dict, repo_name: str) -> BuildData:
        """Parse GitHub Actions workflow run to BuildData."""
        raw_status = run.get("status", "unknown")
        raw_conclusion = run.get("conclusion")

        created_at = None
        if run.get("created_at"):
            created_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))

        started_at = None
        if run.get("run_started_at"):
            started_at = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))

        completed_at = None
        if run.get("updated_at") and raw_status == "completed":
            completed_at = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))

        duration = None
        if started_at and completed_at:
            duration = (completed_at - started_at).total_seconds()

        return BuildData(
            build_id=str(run["id"]),
            build_number=run.get("run_number"),
            repo_name=repo_name,
            branch=run.get("head_branch"),
            commit_sha=run.get("head_sha"),
            commit_message=(
                run.get("head_commit", {}).get("message") if run.get("head_commit") else None
            ),
            commit_author=(
                run.get("head_commit", {}).get("author", {}).get("name")
                if run.get("head_commit")
                else None
            ),
            status=self.normalize_status(raw_status),
            conclusion=self.normalize_conclusion(raw_conclusion),
            created_at=created_at,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            web_url=run.get("html_url"),
            logs_url=run.get("logs_url"),
            provider=CIProvider.GITHUB_ACTIONS,
            raw_data=run,
        )

    def _parse_job(self, job: dict) -> JobData:
        """Parse GitHub Actions job to JobData."""
        started_at = None
        if job.get("started_at"):
            started_at = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))

        completed_at = None
        if job.get("completed_at"):
            completed_at = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))

        duration = None
        if started_at and completed_at:
            duration = (completed_at - started_at).total_seconds()

        return JobData(
            job_id=str(job["id"]),
            job_name=job.get("name", "unknown"),
            status=self.normalize_status(job.get("conclusion") or job.get("status", "unknown")),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
        )

    def get_repo_url(self, repo_name: str) -> str:
        return f"https://github.com/{repo_name}"

    def get_build_url(self, repo_name: str, build_id: str) -> str:
        return f"https://github.com/{repo_name}/actions/runs/{build_id}"
