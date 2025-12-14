"""
Retry decorator for network-dependent Hamilton features.

Features that call external APIs or perform I/O operations should
use this decorator to handle transient failures gracefully.
"""

from functools import wraps
from typing import Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Exceptions that indicate transient failures worth retrying
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)

F = TypeVar("F", bound=Callable)


def with_retry(
    max_attempts: int = 3,
    min_delay: float = 1.0,
    max_delay: float = 60.0,
) -> Callable[[F], F]:
    """
    Decorator to add retry logic to Hamilton feature functions.

    Args:
        max_attempts: Maximum number of retry attempts.
        min_delay: Minimum delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.

    Example:
        @with_retry(max_attempts=3)
        def my_network_feature(...) -> dict:
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_delay, max=max_delay),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            reraise=True,
        )
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
