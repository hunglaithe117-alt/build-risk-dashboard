"""
GitHub Client Resource Provider.

Provides an authenticated GitHub API client for the pipeline.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

from app.pipeline.resources import ResourceProvider, ResourceNames
from app.services.github.github_client import (
    get_app_github_client,
    get_public_github_client,
    GitHubClient,
)

if TYPE_CHECKING:
    from app.pipeline.core.context import ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class GitHubClientHandle:
    """Handle to an authenticated GitHub client."""

    client: GitHubClient
    installation_id: Optional[str]
    is_app_client: bool


class GitHubClientProvider(ResourceProvider):
    """
    Provides an authenticated GitHub API client.

    Uses app installation for private repos, or public client for public repos.
    """

    @property
    def name(self) -> str:
        return ResourceNames.GITHUB_CLIENT

    def initialize(self, context: ExecutionContext) -> GitHubClientHandle:
        repo = context.repo
        db = context.db

        installation_id = repo.installation_id

        if installation_id:
            # Use app client for installed repos
            client_ctx = get_app_github_client(db, installation_id)
            client = client_ctx.__enter__()
            # Store context manager for cleanup
            self._client_context = client_ctx
            is_app_client = True
        else:
            # Use public client (new instance each time)
            client_ctx = get_public_github_client()
            client = client_ctx.__enter__()
            self._client_context = client_ctx
            is_app_client = False

        return GitHubClientHandle(
            client=client,
            installation_id=installation_id,
            is_app_client=is_app_client,
        )

    def cleanup(self, context: "ExecutionContext") -> None:
        if hasattr(self, "_client_context"):
            try:
                self._client_context.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing GitHub client: {e}")
