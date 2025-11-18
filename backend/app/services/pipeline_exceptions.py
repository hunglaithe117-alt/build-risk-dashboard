"""Custom exceptions for the ingestion pipeline."""
from __future__ import annotations


class PipelineError(Exception):
    """Base exception for pipeline failures."""


class PipelineConfigurationError(PipelineError):
    """Raised when required configuration is missing."""


class PipelineRateLimitError(PipelineError):
    """Raised when the upstream service enforces a rate limit."""


class PipelineRetryableError(PipelineError):
    """Raised for transient issues where retrying later may succeed."""
