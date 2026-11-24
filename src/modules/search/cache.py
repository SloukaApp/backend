import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.modules.search.dto import SearchInput
from src.modules.search.errors import SearchCacheUnavailableError
from src.modules.search.parser import PARSER_VERSION

type Operation = Literal["search", "translate", "synonyms"]


class RedisSearchCache:
    def __init__(self, redis: Redis, key_prefix: str, ttl_seconds: int) -> None:
        self.redis = redis
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds

    def key(self, operation: Operation, data: SearchInput, dictionaries: tuple[str, ...]) -> str:
        digest = hashlib.sha256(
            json.dumps([data.query, dictionaries, data.page]).encode()
        ).hexdigest()
        return f"{self.key_prefix}:search:{PARSER_VERSION}:{operation}:{digest}"

    async def get[Result: BaseModel](self, key: str, result_type: type[Result]) -> Result | None:
        try:
            value = await self.redis.get(key)
        except RedisError as exc:
            raise SearchCacheUnavailableError() from exc
        if value is None:
            return None
        try:
            return result_type.model_validate_json(value, strict=True, extra="forbid")
        except ValidationError:
            return None

    async def put(self, key: str, result: BaseModel) -> None:
        try:
            await self.redis.set(key, result.model_dump_json(), ex=self.ttl_seconds)
        except RedisError as exc:
            raise SearchCacheUnavailableError() from exc
