import asyncio
from typing import Protocol

import httpx
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.core.config import VerbumConfig
from src.modules.search.dto import SearchResult
from src.modules.search.errors import (
    SearchCacheUnavailableError,
    SearchInvalidResponseError,
    SearchUnavailableError,
)
from src.modules.search.external import VerbumResponse


class DictionaryClient(Protocol):
    async def search(
        self, query: str, dictionaries: tuple[str, ...], page: int
    ) -> VerbumResponse: ...


class SearchCache(Protocol):
    async def get(self, key: str) -> SearchResult | None: ...

    async def put(self, key: str, result: SearchResult, ttl_seconds: int) -> None: ...


class VerbumClient:
    def __init__(self, client: httpx.AsyncClient, config: VerbumConfig) -> None:
        self.client = client
        self.config = config

    async def search(self, query: str, dictionaries: tuple[str, ...], page: int) -> VerbumResponse:
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.get(
                    str(self.config.url),
                    params={"q": query, "in": ",".join(dictionaries), "page": page},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self.config.max_retries:
                    raise SearchUnavailableError() from exc
            except httpx.HTTPError as exc:
                raise SearchInvalidResponseError() from exc
            else:
                if response.status_code in {429, 502, 503, 504}:
                    if attempt == self.config.max_retries:
                        raise SearchUnavailableError()
                elif response.is_error or response.is_redirect:
                    raise SearchInvalidResponseError()
                else:
                    try:
                        return VerbumResponse.model_validate_json(response.content)
                    except ValidationError as exc:
                        raise SearchInvalidResponseError() from exc
            await asyncio.sleep(0.2 * (2**attempt))
        raise SearchUnavailableError()


class RedisSearchCache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get(self, key: str) -> SearchResult | None:
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
            try:
                return SearchResult.model_validate_json(value)
            except ValidationError:
                # A damaged cache entry is a miss, never a successful empty result.
                return None
        except RedisError as exc:
            raise SearchCacheUnavailableError() from exc

    async def put(self, key: str, result: SearchResult, ttl_seconds: int) -> None:
        try:
            await self.redis.set(key, result.model_dump_json(), ex=ttl_seconds)
        except RedisError as exc:
            raise SearchCacheUnavailableError() from exc
