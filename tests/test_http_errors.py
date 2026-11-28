from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Request, Response, status
from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from src import main
from src.core.config import AppConfig, LoggingConfig, RedisConfig, Settings
from src.core.dependencies import get_uow
from src.core.errors import ApplicationError, RateLimitExceededError, RateLimitUnavailableError
from src.modules.auth.dependencies import get_auth_service, get_principal
from src.modules.auth.errors import InvalidAccessError

ORIGIN = "http://localhost:8000"
REQUEST_ID = "test-request-id"


def raise_test_error(kind: str) -> None:
    match kind:
        case "limited":
            raise RateLimitExceededError(7)
        case "unavailable":
            raise RateLimitUnavailableError("private diagnostic")
        case "unknown":
            raise ApplicationError("private diagnostic")
        case "unexpected":
            raise RuntimeError("private diagnostic")


class FailingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, trusted_hosts: list[str]) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        scope, _, kind = request.url.path.rpartition("/")
        if scope == "/middleware":
            raise_test_error(kind)
        return await call_next(request)


@pytest.fixture
async def api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings.model_construct(
        app=AppConfig(),
        logging=LoggingConfig(),
        redis=RedisConfig.model_validate({"dsn": "redis://localhost:6379"}),
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "ProxyHeadersMiddleware", FailingMiddleware)
    app = main.create_app()
    app.state.redis = SimpleNamespace(eval=AsyncMock(return_value=0))

    for dependency in (get_uow, get_auth_service, get_principal):
        app.dependency_overrides[dependency] = lambda: None

    @app.get("/route/{kind}")
    async def failing_route(kind: str) -> None:
        raise_test_error(kind)

    @app.get("/protected")
    async def protected() -> None:
        raise InvalidAccessError("private diagnostic")

    @app.get("/framework")
    async def framework_error() -> None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "private diagnostic")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Origin": ORIGIN, "X-Request-ID": REQUEST_ID},
    ) as client:
        yield client


@pytest.mark.parametrize("source", ["route", "middleware"])
@pytest.mark.parametrize(
    ("kind", "code", "detail", "retry_after"),
    [
        ("limited", status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests", "7"),
        (
            "unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Rate limit service unavailable",
            None,
        ),
        ("unknown", status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error", None),
        ("unexpected", status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error", None),
    ],
)
async def test_safe_errors_across_http_stack(
    api: httpx.AsyncClient, source: str, kind: str, code: int, detail: str, retry_after: str | None
) -> None:
    response = await api.get(f"/{source}/{kind}")
    assert response.status_code == code
    assert response.json() == {"detail": detail}
    assert response.headers.get("Retry-After") == retry_after
    assert response.headers["X-Request-ID"] == REQUEST_ID
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN


async def test_validation_response_matches_openapi(api: httpx.AsyncClient) -> None:
    password_path = "/api/v1/auth/password"
    response = await api.post(
        password_path, json={"current_password": "dummy-current", "new_password": "short"}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json() == {"detail": "Invalid request"}
    assert response.headers["X-Request-ID"] == REQUEST_ID
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN

    paths = (await api.get("/api/v1/openapi.json")).json()["paths"]
    responses = paths[password_path]["post"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorResponse"
    )
    assert "500" in responses
    assert "Retry-After" in paths["/api/v1/auth/login"]["post"]["responses"]["429"]["headers"]


async def test_http_errors_keep_protocol_headers(api: httpx.AsyncClient) -> None:
    protected = await api.get("/protected")
    assert protected.status_code == status.HTTP_401_UNAUTHORIZED
    assert protected.json() == {"detail": "Invalid or missing access token"}
    assert protected.headers["WWW-Authenticate"] == "Bearer"

    framework = await api.get("/framework")
    assert framework.status_code == status.HTTP_404_NOT_FOUND
    assert framework.json() == {"detail": "Not Found"}

    wrong_method = await api.post("/framework")
    assert wrong_method.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert wrong_method.headers["Allow"] == "GET"
