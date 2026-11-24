import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid7

import httpx
import pytest
from fastapi import Request
from test_search_parser import FIXTURES

from src import main
from src.core.config import (
    AppConfig,
    CacheConfig,
    LoggingConfig,
    RedisConfig,
    Settings,
    VerbumConfig,
    get_settings,
)
from src.modules.auth.dependencies import get_current_user
from src.modules.auth.errors import InvalidAccessError
from src.modules.search.external import VerbumArticle
from src.modules.search.parser import PARSER_VERSION
from src.modules.search.verbum import VerbumClient
from src.modules.users.dto import UserState

FIXTURE_NAMES = {
    "tsblm2022": "tsblm_alternatives",
    "tsbm": "tsbm_notes_phrases",
    "rbs10": "rbs_inline_senses",
    "klyshka": "klyshka_synonyms",
}


class RedisDouble:
    def __init__(self) -> None:
        self.cached: dict[str, str] = {}
        self.writes = 0

    async def get(self, key: str) -> str | None:
        return self.cached.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        assert ex == 30 * 86400
        self.writes += 1
        self.cached[key] = value


class VerbumDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...], int]] = []
        self.failure: str | None = None

    def respond(self, request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        dictionaries = tuple(request.url.params["in"].split(","))
        page = int(request.url.params["page"])
        self.calls.append((query, dictionaries, page))
        if self.failure == "unavailable":
            return httpx.Response(503)

        articles = (
            [
                VerbumArticle.model_validate_json(
                    (FIXTURES / f"{FIXTURE_NAMES[dictionary]}.json").read_bytes()
                ).model_dump()
                for dictionary in reversed(dictionaries)
            ]
            if page < 999
            else []
        )
        if self.failure == "parse":
            articles[0]["Content"] = "<p>Missing headword</p>"
        if self.failure == "foreign":
            articles[-1]["DictionaryID"] = "rbs10"
        if self.failure == "duplicate":
            dictionaries += dictionaries[:1]
        return httpx.Response(
            200,
            json={
                "DictIDs": dictionaries,
                "Q": query,
                "Prefix": "",
                "Articles": articles,
                "TermSuggestions": [f"{dictionaries[0]}:{page}"],
                "Pagination": {
                    "Current": page if page == 999 else page + 1,
                    "Total": len(dictionaries) * 10,
                    "Relation": "upstream",
                },
            },
        )


type DictionaryAPI = tuple[httpx.AsyncClient, Settings, RedisDouble, VerbumDouble, UserState]


@pytest.fixture
async def dictionary_api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[DictionaryAPI]:
    settings = Settings.model_construct(
        app=AppConfig(),
        logging=LoggingConfig(),
        redis=RedisConfig.model_validate({"dsn": "redis://localhost:6379"}),
        cache=CacheConfig(),
        verbum=VerbumConfig(
            dictionary_ids=("tsbm", "klyshka", "rbs10", "tsblm2022"), max_retries=0
        ),
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    account = UserState(
        id=uuid7(),
        email="reader@example.test",
        email_confirmed=True,
        onboarding_completed=False,
        timezone=None,
        reminders_enabled=False,
        reminder_time=None,
        consent_version="test",
        consent_accepted_at=datetime.now(UTC),
    )

    def current_user(request: Request) -> UserState:
        if request.headers.get("Authorization") != "Bearer test":
            raise InvalidAccessError()
        return account

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_settings] = lambda: settings
    redis = RedisDouble()
    upstream = VerbumDouble()
    app.state.redis = redis
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.respond)) as verbum:
        app.state.verbum_client = VerbumClient(verbum, settings.verbum)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer test"},
        ) as api:
            yield api, settings, redis, upstream, account


async def test_routes_and_independent_pages(dictionary_api: DictionaryAPI) -> None:
    api, _, redis, upstream, _ = dictionary_api
    common_keys = {"word", "source"}
    lexical_keys = common_keys | {"alternative_words", "homonym", "grammar", "phrases"}
    cases = (
        ("search", ("tsbm", "tsblm2022"), lexical_keys | {"definitions", "related"}),
        ("translate", ("rbs10",), lexical_keys | {"translations"}),
        ("synonyms", ("klyshka",), common_keys | {"synonyms"}),
    )
    for route, dictionaries, keys in cases:
        bodies = {}
        for page in (1, 1, 999, 999):
            response = await api.get(f"/api/v1/{route}", params={"query": "  ХУТКА ", "page": page})
            assert response.status_code == 200
            body = response.json()
            assert body == bodies.setdefault(page, body)
            assert set(body) == {"query", "items", "suggestions", "pagination"}
            assert body["query"] == "хутка"
            assert body["suggestions"] == [f"{dictionaries[0]}:{page}"]
            assert body["pagination"] == {
                "requested_page": page,
                "upstream_current": 2 if page == 1 else 999,
                "upstream_total": len(dictionaries) * 10,
                "upstream_relation": "upstream",
            }
            if page == 1:
                assert [item["source"]["dictionary_id"] for item in body["items"]] == list(
                    dictionaries
                )
                assert all(set(item) == keys for item in body["items"])
            else:
                assert body["items"] == []
    assert upstream.calls == [
        ("хутка", dictionaries, page) for _, dictionaries, _ in cases for page in (1, 999)
    ]
    assert len(redis.cached) == redis.writes == 6
    for route, _, _ in cases:
        values = [
            json.loads(value)
            for key, value in redis.cached.items()
            if f":search:{PARSER_VERSION}:{route}:" in key
        ]
        assert len(values) == 2
        assert all(
            set(value) == {"query", "items", "suggestions", "pagination"} for value in values
        )


async def test_invalid_cached_result_is_replaced(dictionary_api: DictionaryAPI) -> None:
    api, _, redis, upstream, _ = dictionary_api
    path = "/api/v1/translate"
    params = {"query": "собака"}
    first = await api.get(path, params=params)
    assert first.status_code == 200
    (key,) = redis.cached
    redis.cached[key] = '{"articles": []}'

    second = await api.get(path, params=params)
    assert second.status_code == 200
    assert second.json() == first.json()
    assert json.loads(redis.cached[key]) == first.json()
    assert len(upstream.calls) == 2


async def test_disabled_operation_skips_upstream(dictionary_api: DictionaryAPI) -> None:
    api, settings, redis, upstream, _ = dictionary_api
    settings.verbum = VerbumConfig(dictionary_ids=("tsbm", "klyshka"))
    assert (await api.get("/api/v1/translate", params={"query": "x"})).status_code == 503
    assert not upstream.calls
    assert not redis.cached


async def test_upstream_errors_are_not_cached(dictionary_api: DictionaryAPI) -> None:
    api, _, redis, upstream, _ = dictionary_api
    for failure in ("parse", "foreign", "duplicate", "unavailable", None):
        upstream.failure = failure
        response = await api.get("/api/v1/search", params={"query": "x"})
        assert response.status_code == {None: 200, "unavailable": 503}.get(failure, 502)
        assert len(redis.cached) == int(failure is None)
    assert len(upstream.calls) == 5


async def test_validation_auth_and_openapi(dictionary_api: DictionaryAPI) -> None:
    api, _, redis, upstream, account = dictionary_api
    spec = (await api.get("/api/v1/openapi.json")).json()
    for route, model in (
        ("search", "SearchResponse"),
        ("translate", "TranslateResponse"),
        ("synonyms", "SynonymsResponse"),
    ):
        path = f"/api/v1/{route}"
        responses = spec["paths"][path]["get"]["responses"]
        assert set(responses) == {"200", "401", "403", "422", "502", "503"}
        assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(model)
        assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
            "/HTTPValidationError"
        )

        assert (await api.get(path, headers={"Authorization": ""})).status_code == 401
        account.email_confirmed = False
        assert (await api.get(path, params={"query": "x"})).status_code == 403
        account.email_confirmed = True
        for params in ({}, {"query": "\tx"}, {"query": " "}, {"query": "x", "page": 0}):
            assert (await api.get(path, params=params)).status_code == 422
    assert not redis.cached
    assert not upstream.calls
