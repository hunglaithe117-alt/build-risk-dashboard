"""
Sliding window rate limiter to prevent burst requests to GitHub API.

This helps avoid secondary rate limits caused by too many requests
in a short time window.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class SlidingWindowRateLimiter:
    """
    Thread-safe sliding window rate limiter with burst allowance.

    Features:
    - Burst allowance for initial requests
    - Smooth request distribution over time
    - Thread-safe for concurrent access
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        burst_allowance: int = 5,
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_second: Maximum sustained request rate
            burst_allowance: Number of instant requests allowed before throttling
        """
        self.interval = 1.0 / requests_per_second
        self.burst_allowance = burst_allowance
        self._last_request_time = 0.0
        self._burst_tokens = burst_allowance
        self._lock = threading.Lock()

    def wait(self) -> float:
        """
        Wait if necessary to respect rate limit.

        Returns:
            The time waited in seconds.
        """
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time

            # Refill burst tokens based on elapsed time
            if self._last_request_time > 0:
                tokens_to_add = int(elapsed / self.interval)
                self._burst_tokens = min(
                    self.burst_allowance, self._burst_tokens + tokens_to_add
                )

            if self._burst_tokens > 0:
                # Use a burst token (instant)
                self._burst_tokens -= 1
                self._last_request_time = now
                return 0.0

            # Must wait for next slot
            wait_time = self.interval - (elapsed % self.interval)
            if wait_time > 0:
                time.sleep(wait_time)

            self._last_request_time = time.time()
            return wait_time

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        with self._lock:
            self._last_request_time = 0.0
            self._burst_tokens = self.burst_allowance


_rate_limiter: Optional[SlidingWindowRateLimiter] = None


def get_rate_limiter() -> SlidingWindowRateLimiter:
    """Get or create the global rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        # Default: 10 requests/second with 5 burst allowance
        # This is conservative to avoid secondary rate limits
        _rate_limiter = SlidingWindowRateLimiter(
            requests_per_second=10.0,
            burst_allowance=5,
        )
    return _rate_limiter
