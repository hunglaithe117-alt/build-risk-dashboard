"""
SonarQube Resource Provider - Provides SonarQube client for feature extraction.

This resource provider initializes the MetricsExporter client that can:
1. Scan commits via SonarQube
2. Fetch measures/metrics from SonarQube API
"""

from __future__ import annotations

import logging

from app.pipeline.resources import ResourceProvider
from app.services.sonar.exporter import MetricsExporter
from app.services.sonar.runner import SonarCommitRunner
from app.config import settings
from app.pipeline.core.context import ExecutionContext

logger = logging.getLogger(__name__)


class SonarClientProvider(ResourceProvider):
    """
    Provides SonarQube client for feature extraction.

    The client can:
    - Scan commits and create SonarQube projects
    - Fetch quality metrics from existing projects
    """

    @property
    def name(self) -> str:
        return "sonar_client"

    def initialize(self, context: ExecutionContext) -> SonarClient:
        """
        Initialize and return a SonarQube client.

        Returns:
            SonarClient with access to both scanner and exporter
        """
        # Get repo info for project key
        repo = context.repo
        project_key_prefix = getattr(
            settings, "SONAR_DEFAULT_PROJECT_KEY", "build-risk"
        )
        project_key = (
            f"{project_key_prefix}_{repo.name if hasattr(repo, 'name') else 'unknown'}"
        )

        return SonarClient(
            project_key=project_key,
            exporter=MetricsExporter(),
        )

    def cleanup(self, context: "ExecutionContext") -> None:
        """Cleanup SonarQube resources if needed."""
        pass


class SonarClient:
    """
    Wrapper around SonarQube services for pipeline use.

    Provides:
    - scan_commit(): Run SonarQube analysis on a specific commit
    - get_measures(): Fetch measures from existing SonarQube project
    """

    def __init__(self, project_key: str, exporter: MetricsExporter):
        self.project_key = project_key
        self.exporter = exporter
        self._runner = None

    @property
    def runner(self) -> SonarCommitRunner:
        """Lazy-load SonarCommitRunner."""
        if self._runner is None:
            self._runner = SonarCommitRunner(self.project_key)
        return self._runner

    def scan_commit(
        self, repo_url: str, commit_sha: str, config_content: str = None
    ) -> str:
        """
        Run SonarQube scan on a specific commit.

        Args:
            repo_url: Repository URL to clone
            commit_sha: Commit SHA to scan
            config_content: Optional custom sonar-project.properties content

        Returns:
            Component key of the scanned project
        """
        return self.runner.scan_commit(repo_url, commit_sha, config_content)

    def get_measures(self, component_key: str) -> dict:
        """
        Fetch measures from SonarQube API.

        Args:
            component_key: SonarQube component key

        Returns:
            Dict of metric_key -> value
        """
        return self.exporter.collect_metrics(component_key)

    def get_metrics_list(self) -> list:
        """Get list of all configured metrics."""
        return self.exporter.metrics
