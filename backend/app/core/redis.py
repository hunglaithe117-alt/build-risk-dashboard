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


def get_redis() -> redis.Redis:
    """Get sync Redis client."""
    return RedisClient.get_client()


async def get_async_redis() -> aioredis.Redis:
    """Get async Redis client."""
    return await AsyncRedisClient.get_client()
