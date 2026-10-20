from taskiq import AsyncBroker
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.core.config import Settings


def build_broker(settings: Settings) -> AsyncBroker:
    url = settings.redis.url
    return ListQueueBroker(url=url).with_result_backend(
        RedisAsyncResultBackend(redis_url=url),
    )
