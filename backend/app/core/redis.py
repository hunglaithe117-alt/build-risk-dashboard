import redis
import redis.asyncio as aioredis

from app.config import settings


class RedisClient:
    _client = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._client is None:
            cls._client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return cls._client


class AsyncRedisClient:
    _client = None

    @classmethod
    async def get_client(cls) -> aioredis.Redis:
        if cls._client is None:
            cls._client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return cls._client


class RedisLock:
    """
    Redis-based distributed lock for preventing concurrent operations.

    Usage:
        with RedisLock("clone:repo_id", timeout=600):
            # critical section
    """

    def __init__(self, key: str, timeout: int = 600, blocking_timeout: int = 30):
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.blocking_timeout = blocking_timeout
        self._lock = None

    def __enter__(self):
        redis_client = redis.from_url(settings.REDIS_URL)
        self._lock = redis_client.lock(
            self.key,
            timeout=self.timeout,
            blocking_timeout=self.blocking_timeout,
        )
        acquired = self._lock.acquire(blocking=True)
        if not acquired:
            raise TimeoutError(f"Could not acquire lock: {self.key}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._lock:
            try:
                self._lock.release()
            except Exception:
                pass  # Lock may have expired
        return False


def get_redis() -> redis.Redis:
    """Get sync Redis client."""
    return RedisClient.get_client()


async def get_async_redis() -> aioredis.Redis:
    """Get async Redis client."""
    return await AsyncRedisClient.get_client()
