"""Tests for GitHub token pool and rate limiting improvements."""

import time
import pytest
from unittest.mock import MagicMock, patch


class TestSlidingWindowRateLimiter:
    """Tests for SlidingWindowRateLimiter."""

    def test_burst_allowance(self):
        """Test that burst allowance allows instant requests."""
        from app.services.github.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(requests_per_second=10.0, burst_allowance=3)

        # First 3 requests should be instant (burst)
        for i in range(3):
            wait_time = limiter.wait()
            assert wait_time == 0.0, f"Request {i+1} should have been instant"

    def test_throttling_after_burst(self):
        """Test that requests are throttled after burst is exhausted."""
        from app.services.github.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(
            requests_per_second=100.0,  # 10ms interval
            burst_allowance=1,
        )

        # Use up the burst
        wait_time = limiter.wait()
        assert wait_time == 0.0

        # Next request should be throttled
        wait_time = limiter.wait()
        assert wait_time > 0.0

    def test_reset(self):
        """Test that reset restores burst tokens."""
        from app.services.github.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter(requests_per_second=10.0, burst_allowance=2)

        # Exhaust burst
        limiter.wait()
        limiter.wait()

        # Reset
        limiter.reset()

        # Should have burst again
        wait_time = limiter.wait()
        assert wait_time == 0.0


class TestGitHubCache:
    """Tests for ETag-based caching."""

    @patch("app.services.github.github_cache.get_redis")
    def test_cache_miss(self, mock_get_redis):
        """Test cache returns None on miss."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {}
        mock_get_redis.return_value = mock_redis

        from app.services.github.github_cache import GitHubCache

        cache = GitHubCache()
        etag, last_modified, data = cache.get_cached("https://api.github.com/test")

        assert etag is None
        assert last_modified is None
        assert data is None

    @patch("app.services.github.github_cache.get_redis")
    def test_cache_hit(self, mock_get_redis):
        """Test cache returns data on hit."""
        mock_redis = MagicMock()
        mock_redis.hgetall.return_value = {
            "etag": '"abc123"',
            "data": '{"test": "data"}',
        }
        mock_get_redis.return_value = mock_redis

        from app.services.github.github_cache import GitHubCache

        cache = GitHubCache()
        etag, last_modified, data = cache.get_cached("https://api.github.com/test")

        assert etag == '"abc123"'
        assert data == {"test": "data"}

    @patch("app.services.github.github_cache.get_redis")
    def test_set_cached(self, mock_get_redis):
        """Test cache stores data correctly."""
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        from app.services.github.github_cache import GitHubCache

        cache = GitHubCache()
        result = cache.set_cached(
            "https://api.github.com/test",
            {"test": "data"},
            etag='"abc123"',
        )

        assert result is True
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()


class TestGitHubSecondaryRateLimit:
    """Tests for secondary rate limit handling."""

    def test_exception_inheritance(self):
        """Test that secondary rate limit inherits from rate limit."""
        from app.services.github.exceptions import (
            GithubRateLimitError,
            GithubSecondaryRateLimitError,
        )

        exc = GithubSecondaryRateLimitError("test", retry_after=120)

        assert isinstance(exc, GithubRateLimitError)
        assert exc.retry_after == 120
