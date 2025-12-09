"""
ETag-based caching for GitHub API responses.

Conditional requests with ETags don't count against rate limits when
the resource hasn't changed (returns 304 Not Modified).

This can reduce API quota usage by up to 90% for frequently accessed
resources like repository info, workflow runs, etc.
"""

from __future__ import annotations

import json
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Any

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key prefix for cache entries
KEY_PREFIX = "github_cache:"

# Default TTL for cache entries (1 hour)
DEFAULT_TTL = 3600

# Extended TTL for stable resources (24 hours)
EXTENDED_TTL = 86400


class GitHubCache:
    """
    Redis-backed ETag cache for GitHub API responses.

    Features:
    - Store ETag and Last-Modified headers for conditional requests
    - Automatic TTL management
    - Thread-safe via Redis
    """

    def __init__(self):
        self._redis = get_redis()

    def _cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"{KEY_PREFIX}{url_hash}"

    def get_cached(
        self, url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
        """
        Get cached ETag, Last-Modified, and data for a URL.

        Args:
            url: The API URL

        Returns:
            Tuple of (etag, last_modified, cached_data)
        """
        try:
            key = self._cache_key(url)
            cached = self._redis.hgetall(key)

            if not cached:
                return None, None, None

            etag = cached.get("etag") or cached.get(b"etag")
            last_modified = cached.get("last_modified") or cached.get(b"last_modified")
            data_str = cached.get("data") or cached.get(b"data")

            # Handle bytes from Redis
            if isinstance(etag, bytes):
                etag = etag.decode()
            if isinstance(last_modified, bytes):
                last_modified = last_modified.decode()
            if isinstance(data_str, bytes):
                data_str = data_str.decode()

            data = json.loads(data_str) if data_str else None

            return etag, last_modified, data

        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None, None, None

    def set_cached(
        self,
        url: str,
        data: Any,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        ttl: int = DEFAULT_TTL,
    ) -> bool:
        """
        Cache response with ETag and/or Last-Modified.

        Args:
            url: The API URL
            data: Response data to cache
            etag: ETag header value
            last_modified: Last-Modified header value
            ttl: Time-to-live in seconds

        Returns:
            True if cached successfully
        """
        if not etag and not last_modified:
            # No cache headers, skip caching
            return False

        try:
            key = self._cache_key(url)
            cache_data = {
                "data": json.dumps(data),
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }

            if etag:
                cache_data["etag"] = etag
            if last_modified:
                cache_data["last_modified"] = last_modified

            self._redis.hset(key, mapping=cache_data)
            self._redis.expire(key, ttl)

            return True

        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
            return False

    def invalidate(self, url: str) -> bool:
        """
        Invalidate cache entry for a URL.

        Args:
            url: The API URL to invalidate

        Returns:
            True if entry was deleted
        """
        try:
            key = self._cache_key(url)
            return self._redis.delete(key) > 0
        except Exception as e:
            logger.warning(f"Cache invalidate failed: {e}")
            return False

    def get_stats(self) -> dict:
        """Get cache statistics."""
        try:
            # Count cache entries
            pattern = f"{KEY_PREFIX}*"
            keys = list(self._redis.scan_iter(match=pattern, count=100))
            return {
                "entries": len(keys),
                "prefix": KEY_PREFIX,
            }
        except Exception:
            return {"entries": 0, "prefix": KEY_PREFIX}


_cache: Optional[GitHubCache] = None


def get_github_cache() -> GitHubCache:
    """Get or create the global GitHub cache singleton."""
    global _cache
    if _cache is None:
        _cache = GitHubCache()
    return _cache
