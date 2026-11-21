import hashlib
import json
from uuid import UUID

from src.core.rate_limit import RateLimiter
from src.modules.search.adapters import DictionaryClient, SearchCache
from src.modules.search.dto import Pagination, SearchInput, SearchResult
from src.modules.search.errors import SearchInvalidResponseError
from src.modules.search.parser import PARSER_VERSION, parse_article


class SearchService:
    def __init__(
        self,
        client: DictionaryClient,
        cache: SearchCache,
        limiter: RateLimiter,
        dictionaries: tuple[str, ...],
        key_prefix: str,
        ttl_seconds: int,
        window_seconds: int,
        max_requests: int,
    ) -> None:
        self.client = client
        self.cache = cache
        self.limiter = limiter
        self.dictionaries = dictionaries
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds
        self.window_seconds = window_seconds
        self.max_requests = max_requests

    async def search(self, account_id: UUID, data: SearchInput) -> SearchResult:
        """Search outside DB scopes.

        Raises SearchInvalidResponseError, SearchUnavailableError,
        SearchCacheUnavailableError, RateLimitExceededError or RateLimitUnavailableError.
        Search owns this use case; auth supplies a materialized confirmed account.
        """
        await self.limiter.check_many(
            [(f"search:account:{account_id}", self.window_seconds, self.max_requests)]
        )
        digest = hashlib.sha256(
            json.dumps([data.query, self.dictionaries, data.page, PARSER_VERSION]).encode()
        ).hexdigest()
        key = f"{self.key_prefix}:search:{PARSER_VERSION}:{digest}"
        cached = await self.cache.get(key)
        if cached is not None:
            return cached
        upstream = await self.client.search(data.query, self.dictionaries, data.page)
        if set(upstream.DictIDs) != set(self.dictionaries) or any(
            article.DictionaryID not in self.dictionaries for article in upstream.Articles
        ):
            raise SearchInvalidResponseError()
        try:
            articles = [parse_article(article) for article in upstream.Articles]
        except (ValueError, KeyError, RecursionError, AssertionError) as exc:
            raise SearchInvalidResponseError() from exc
        articles.sort(key=lambda article: self.dictionaries.index(article.dictionary_id))
        result = SearchResult(
            query=data.query,
            articles=articles,
            term_suggestions=upstream.TermSuggestions,
            pagination=Pagination(
                requested_page=data.page,
                upstream_current=upstream.Pagination.Current,
                upstream_total=upstream.Pagination.Total,
                upstream_relation=upstream.Pagination.Relation,
            ),
        )
        await self.cache.put(key, result, self.ttl_seconds)
        return result
