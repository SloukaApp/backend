from redis.asyncio import Redis

from src.core.config import RedisConfig


def build_redis(config: RedisConfig) -> Redis:
    client: Redis = Redis.from_url(
        config.url,
        max_connections=config.max_connections,
        socket_timeout=config.socket_timeout,
        decode_responses=True,
    )
    return client
