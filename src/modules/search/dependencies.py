from typing import Annotated, cast

from fastapi import Depends, Request

from src.core.dependencies import RedisDep, SettingsDep
from src.modules.search.cache import RedisSearchCache
from src.modules.search.service import SearchService
from src.modules.search.verbum import VerbumClient


def get_search_service(request: Request, redis: RedisDep, settings: SettingsDep) -> SearchService:
    return SearchService(
        client=cast(VerbumClient, request.app.state.verbum_client),
        cache=RedisSearchCache(
            redis, key_prefix=settings.redis.key_prefix, ttl_seconds=settings.cache.ttl_days * 86400
        ),
        dictionaries=settings.verbum.dictionary_ids,
    )


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]
