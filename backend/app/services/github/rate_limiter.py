"""
Redis-based sliding window rate limiter for distributed workloads.

This module provides a thread-safe, multi-process safe rate limiter using Redis
for state management. It prevents GitHub secondary rate limits (abuse detection)
by limiting request frequency across all Celery workers.

Redis Keys:
- github:ratelimit:requests - Sorted set of request timestamps (sliding window)
- github:ratelimit:burst - Current burst tokens available
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import redis

from app.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key constants
KEY_REQUESTS = "github:ratelimit:requests"
KEY_BURST = "github:ratelimit:burst"


class RedisRateLimiter:
    """
    Redis-backed sliding window rate limiter with burst allowance.

    Features:
    - Atomic operations across multiple processes/workers
    - Sliding window for smooth request distribution
    - Burst allowance for initial requests
    - Automatic cleanup of old entries
    """

    def __init__(
        self,
        key_prefix: str = "github:ratelimit",
        requests_per_second: float = 10.0,
        burst_allowance: int = 5,
        window_size: float = 1.0,
    ):
        """
        Initialize Redis rate limiter.

        Args:
            key_prefix: Redis key prefix for this limiter instance
            requests_per_second: Maximum sustained request rate
            burst_allowance: Number of instant requests allowed before throttling
            window_size: Sliding window size in seconds
        """
        self._redis: redis.Redis = get_redis()
        self._key_requests = f"{key_prefix}:requests"
        self._key_burst = f"{key_prefix}:burst"
        self._requests_per_second = requests_per_second
        self._burst_allowance = burst_allowance
        self._window_size = window_size
        self._min_interval = 1.0 / requests_per_second

        # Lua script for atomic rate limit check and acquire
        self._acquire_script = self._redis.register_script("""
            local requests_key = KEYS[1]
            local burst_key = KEYS[2]
            local now = tonumber(ARGV[1])
            local window_size = tonumber(ARGV[2])
            local max_requests = tonumber(ARGV[3])
            local burst_allowance = tonumber(ARGV[4])
            local min_interval = tonumber(ARGV[5])

            -- Clean up old entries outside the window
            local window_start = now - window_size
            redis.call('ZREMRANGEBYSCORE', requests_key, '-inf', window_start)

            -- Get current request count in window
            local current_count = redis.call('ZCARD', requests_key)

            -- Check burst tokens first
            local burst_tokens = tonumber(redis.call('GET', burst_key) or burst_allowance)

            if burst_tokens > 0 then
                -- Use a burst token
                redis.call('SET', burst_key, burst_tokens - 1, 'EX', 60)
                redis.call('ZADD', requests_key, now, now .. ':' .. math.random())
                redis.call('EXPIRE', requests_key, math.ceil(window_size) + 1)
                return 0  -- No wait needed
            end

            -- No burst tokens, check if we can proceed
            if current_count < max_requests then
                -- Can proceed immediately
                redis.call('ZADD', requests_key, now, now .. ':' .. math.random())
                redis.call('EXPIRE', requests_key, math.ceil(window_size) + 1)
                return 0
            end

            -- Need to wait - find the oldest request and calculate wait time
            local oldest = redis.call('ZRANGE', requests_key, 0, 0, 'WITHSCORES')
            if #oldest >= 2 then
                local oldest_time = tonumber(oldest[2])
                local wait_until = oldest_time + window_size
                local wait_time = wait_until - now
                if wait_time > 0 then
                    return wait_time
                end
            end

            return min_interval
        """)

        # Lua script to refill burst tokens
        self._refill_script = self._redis.register_script("""
            local burst_key = KEYS[1]
            local burst_allowance = tonumber(ARGV[1])
            local refill_rate = tonumber(ARGV[2])  -- tokens per second
            local now = tonumber(ARGV[3])

            local last_refill_key = burst_key .. ':last_refill'
            local last_refill = tonumber(redis.call('GET', last_refill_key) or 0)

            if last_refill == 0 then
                -- First time, set burst to full
                redis.call('SET', burst_key, burst_allowance, 'EX', 60)
                redis.call('SET', last_refill_key, now, 'EX', 60)
                return burst_allowance
            end

            local elapsed = now - last_refill
            local tokens_to_add = math.floor(elapsed * refill_rate)

            if tokens_to_add > 0 then
                local current = tonumber(redis.call('GET', burst_key) or 0)
                local new_tokens = math.min(burst_allowance, current + tokens_to_add)
                redis.call('SET', burst_key, new_tokens, 'EX', 60)
                redis.call('SET', last_refill_key, now, 'EX', 60)
                return new_tokens
            end

            return tonumber(redis.call('GET', burst_key) or 0)
        """)

    def wait(self) -> float:
        """
        Wait if necessary to respect rate limit.

        This is thread-safe and process-safe across multiple workers.

        Returns:
            The time waited in seconds.
        """
        total_waited = 0.0
        max_attempts = 10  # Prevent infinite loop

        for _ in range(max_attempts):
            now = time.time()

            # First, try to refill burst tokens
            self._refill_burst(now)

            # Try to acquire a slot
            wait_time = self._acquire_script(
                keys=[self._key_requests, self._key_burst],
                args=[
                    now,
                    self._window_size,
                    int(self._requests_per_second * self._window_size),
                    self._burst_allowance,
                    self._min_interval,
                ],
            )

            if isinstance(wait_time, bytes):
                wait_time = float(wait_time)
            else:
                wait_time = float(wait_time or 0)

            if wait_time <= 0:
                return total_waited

            # Cap wait time to prevent excessive blocking
            wait_time = min(wait_time, 2.0)
            time.sleep(wait_time)
            total_waited += wait_time

        # If we exhausted attempts, still return (don't block forever)
        logger.warning(
            f"Rate limiter: exhausted {max_attempts} attempts, "
            f"total waited: {total_waited:.2f}s"
        )
        return total_waited

    def _refill_burst(self, now: float) -> int:
        """Refill burst tokens based on elapsed time."""
        return self._refill_script(
            keys=[self._key_burst],
            args=[
                self._burst_allowance,
                self._requests_per_second / 2,  # Refill at half rate
                now,
            ],
        )

    def try_acquire(self) -> bool:
        """
        Non-blocking attempt to acquire a rate limit slot.

        Returns:
            True if acquired, False if should wait.
        """
        now = time.time()
        self._refill_burst(now)

        wait_time = self._acquire_script(
            keys=[self._key_requests, self._key_burst],
            args=[
                now,
                self._window_size,
                int(self._requests_per_second * self._window_size),
                self._burst_allowance,
                self._min_interval,
            ],
        )

        if isinstance(wait_time, bytes):
            wait_time = float(wait_time)

        return wait_time <= 0

    def reset(self) -> None:
        """Reset the rate limiter to initial state."""
        pipe = self._redis.pipeline()
        pipe.delete(self._key_requests)
        pipe.set(self._key_burst, self._burst_allowance, ex=60)
        pipe.execute()


# Module-level singleton
_rate_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter() -> RedisRateLimiter:
    """Get or create the global Redis rate limiter singleton."""
    global _rate_limiter

    if _rate_limiter is None:
        _rate_limiter = RedisRateLimiter(
            requests_per_second=getattr(settings, "GITHUB_API_RATE_PER_SECOND", 10.0),
            burst_allowance=getattr(settings, "GITHUB_API_BURST_ALLOWANCE", 5),
        )

    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the rate limiter singleton (useful for testing)."""
    global _rate_limiter
    if _rate_limiter:
        _rate_limiter.reset()
    _rate_limiter = None
