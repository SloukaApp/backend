from typing import Annotated, cast

from fastapi import Depends, Request

from src.core.dependencies import RedisDep, SettingsDep
from src.core.rate_limit import RateLimiter
from src.modules.search.adapters import DictionaryClient, RedisSearchCache
from src.modules.search.service import SearchService


def get_search_service(request: Request, redis: RedisDep, settings: SettingsDep) -> SearchService:
    return SearchService(
        client=cast(DictionaryClient, request.app.state.verbum_client),
        cache=RedisSearchCache(redis),
        limiter=RateLimiter(redis, settings.redis.key_prefix),
        dictionaries=settings.verbum.dictionary_ids,
        key_prefix=settings.redis.key_prefix,
        ttl_seconds=settings.cache.ttl_days * 86400,
        window_seconds=settings.rate_limit.search_window_seconds,
        max_requests=settings.rate_limit.search_max_requests,
    )


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
