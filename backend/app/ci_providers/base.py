from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from .models import BuildData, CIProvider, JobData, LogFile, ProviderConfig


class CIProviderInterface(ABC):
    def __init__(self, config: ProviderConfig):
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        pass

    @property
    @abstractmethod
    def provider_type(self) -> CIProvider:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
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
        """
        Fetch builds from the CI provider.

        Args:
            repo_name: Repository name
            since: Only fetch builds after this time
            limit: Maximum number of builds per page (default: 100)
            page: Page number for pagination (1-indexed)
            branch: Filter by branch name
            only_with_logs: If True, only fetch builds with available logs
            exclude_bots: If True, skip builds triggered by bot commits
            only_completed: If True, only fetch builds that have completed

        Returns:
            List of normalized BuildData objects for this page
        """
        pass

    @abstractmethod
    async def fetch_build_details(self, build_id: str) -> Optional[BuildData]:
        """
        Fetch detailed information for a specific build.

        Args:
            build_id: Build identifier

        Returns:
            BuildData with full details, or None if not found
        """
        pass

    @abstractmethod
    async def fetch_build_jobs(self, build_id: str) -> List[JobData]:
        """
        Fetch jobs/steps within a build.

        Args:
            build_id: Build identifier

        Returns:
            List of JobData for each job in the build
        """
        pass

    @abstractmethod
    async def fetch_build_logs(
        self,
        build_id: str,
        job_id: Optional[str] = None,
    ) -> List[LogFile]:
        """
        Fetch logs for a build or specific job.

        Args:
            build_id: Build identifier
            job_id: Optional specific job ID

        Returns:
            List of LogFile objects with content
        """
        pass

    @abstractmethod
    def normalize_status(self, raw_status: str) -> str:
        """
        Normalize provider-specific status to BuildStatus enum.

        Args:
            raw_status: Status string from provider API

        Returns:
            Normalized status string matching BuildStatus enum
        """
        pass

    def get_repo_url(self, repo_name: str) -> str:
        """Get web URL for repository."""
        raise NotImplementedError

    def get_build_url(self, repo_name: str, build_id: str) -> str:
        """Get web URL for a specific build."""
        raise NotImplementedError

    def is_build_completed(self, build_data: BuildData) -> bool:
        """
        Check if a BuildData object represents a completed build.

        Args:
            build_data: BuildData object from fetch_build_details

        Returns:
            True if the build is in a final state, False otherwise
        """
        from app.ci_providers.models import BuildStatus

        # Completed status means the build has finished (regardless of conclusion)
        return build_data.status == BuildStatus.COMPLETED

    def wait_rate_limit(self) -> None:
        """
        Wait if necessary to respect provider-specific rate limits.

        Subclasses should override this to implement provider-specific
        rate limiting. Default implementation is a no-op.

        This should be called before making API requests that could
        trigger rate limits.
        """
        pass  # No-op by default - providers override as needed
