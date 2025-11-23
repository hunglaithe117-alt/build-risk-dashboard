"""Custom exceptions for the ingestion pipeline."""

from __future__ import annotations


class GithubError(Exception):
    """Base exception for pipeline failures."""


class GithubConfigurationError(GithubError):
    """Raised when required configuration is missing."""


class GithubRateLimitError(GithubError):
    """Raised when the upstream service enforces a rate limit."""

    def __init__(self, message: str, retry_after: int | float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class GithubRetryableError(GithubError):
    """Raised for transient issues where retrying later may succeed."""


class GithubAllRateLimitError(GithubError):
    """Raised when all GitHub tokens hit rate limits."""

    def __init__(self, message: str, retry_after: int | float | None = None):
        super().__init__(message)
        self.retry_after = retry_after
