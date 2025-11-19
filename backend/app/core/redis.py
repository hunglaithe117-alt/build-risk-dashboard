import redis
from app.config import settings


class RedisClient:
    _client = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._client is None:
            cls._client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return cls._client


def get_redis() -> redis.Redis:
    return RedisClient.get_client()
