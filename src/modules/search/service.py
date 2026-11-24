from collections.abc import Callable

from src.modules.search.cache import Operation, RedisSearchCache
from src.modules.search.dto import (
    DictionaryEntry,
    DictionaryResult,
    Pagination,
    SearchInput,
    SearchResult,
    SynonymsResult,
    TranslateResult,
)
from src.modules.search.errors import SearchInvalidResponseError, SearchUnavailableError
from src.modules.search.external import VerbumArticle
from src.modules.search.projections import search_entries, synonyms_entries, translate_entries
from src.modules.search.verbum import VerbumClient


class SearchService:
    def __init__(
        self, client: VerbumClient, cache: RedisSearchCache, dictionaries: tuple[str, ...]
    ) -> None:
        self.client = client
        self.cache = cache
        self.dictionaries = dictionaries

    async def search(self, data: SearchInput) -> SearchResult:
        """Return definitions outside DB scopes.

        Raises SearchInvalidResponseError, SearchUnavailableError,
        or SearchCacheUnavailableError.
        """
        return await self._lookup(
            "search", data, {"tsblm2022", "tsbm"}, SearchResult, search_entries
        )

    async def translate(self, data: SearchInput) -> TranslateResult:
        """Return Russian–Belarusian translations. Raises the same errors as search."""
        return await self._lookup("translate", data, {"rbs10"}, TranslateResult, translate_entries)

    async def synonyms(self, data: SearchInput) -> SynonymsResult:
        """Return Belarusian synonyms. Raises the same errors as search."""
        return await self._lookup("synonyms", data, {"klyshka"}, SynonymsResult, synonyms_entries)

    async def _lookup[Entry: DictionaryEntry](
        self,
        operation: Operation,
        data: SearchInput,
        operation_dictionaries: set[str],
        result_type: type[DictionaryResult[Entry]],
        entries_from: Callable[[VerbumArticle], list[Entry]],
    ) -> DictionaryResult[Entry]:
        dictionaries = tuple(
            value for value in self.dictionaries if value in operation_dictionaries
        )
        if not dictionaries:
            raise SearchUnavailableError()

        key = self.cache.key(operation, data, dictionaries)
        cached = await self.cache.get(key, result_type)
        if cached is not None:
            return cached

        upstream = await self.client.search(data.query, dictionaries, data.page)
        if sorted(upstream.DictIDs) != sorted(dictionaries) or any(
            article.DictionaryID not in dictionaries for article in upstream.Articles
        ):
            raise SearchInvalidResponseError()
        articles = sorted(
            upstream.Articles, key=lambda article: dictionaries.index(article.DictionaryID)
        )
        try:
            items = [entry for article in articles for entry in entries_from(article)]
        except (ValueError, KeyError, RecursionError, AssertionError) as exc:
            raise SearchInvalidResponseError() from exc

        result = result_type(
            query=data.query,
            items=items,
            suggestions=upstream.TermSuggestions,
            pagination=Pagination(
                requested_page=data.page,
                upstream_current=upstream.Pagination.Current,
                upstream_total=upstream.Pagination.Total,
                upstream_relation=upstream.Pagination.Relation,
            ),
        )
        await self.cache.put(key, result)
        return result
