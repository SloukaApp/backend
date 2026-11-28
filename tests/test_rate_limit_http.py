from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src import main
from src.core.config import AppConfig, RedisConfig, Settings, get_settings
from src.core.dependencies import get_uow
from src.modules.auth.dependencies import get_auth_service
from src.modules.auth.errors import (
    InvalidAccessError,
    InvalidConfirmationError,
    InvalidPasswordResetError,
)

API = "/api/v1"
LOGIN = f"{API}/auth/login"
CONFIRM = f"{API}/auth/confirm-email"
RESET_CONFIRM = f"{API}/auth/password-reset/confirm"
ORIGIN = "http://localhost:8000"
IP = "192.0.2.10"
OTHER_IP = "192.0.2.20"
PREFIX = "slouka:rate_limit:{rate_limit}:"


@pytest.fixture
async def api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncMock]]:
    settings = Settings.model_construct(
        app=AppConfig(trusted_proxies=["127.0.0.1"]),
        redis=RedisConfig.model_validate({"dsn": "redis://localhost:6379"}),
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_uow] = lambda: AsyncMock()
    auth = SimpleNamespace(
        login=AsyncMock(side_effect=InvalidAccessError),
        confirm_email=AsyncMock(side_effect=InvalidConfirmationError),
        confirm_password_reset=AsyncMock(side_effect=InvalidPasswordResetError),
    )
    app.dependency_overrides[get_auth_service] = lambda: auth
    evaluate = AsyncMock(return_value=0)
    app.state.redis = SimpleNamespace(eval=evaluate)

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Origin": ORIGIN, "X-Request-ID": "rate-limit-test", "X-Forwarded-For": IP},
    ) as client:
        yield client, evaluate


async def test_ip_budgets_are_checked_together_before_body_validation(
    api: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    client, evaluate = api
    assert (await client.post(LOGIN, json={})).status_code == 422
    assert (await client.get(LOGIN)).status_code == 405
    assert (await client.get(f"{API}/openapi.json")).status_code == 200
    assert (await client.get(f"{API}/docs")).status_code == 200
    assert (await client.get(f"{API}0/anything")).status_code == 404
    assert [call.args[1:] for call in evaluate.await_args_list] == [
        (2, f"{PREFIX}api:ip:{IP}", f"{PREFIX}login:ip:{IP}", 60, 60, 60, 10),
        (1, f"{PREFIX}api:ip:{IP}", 60, 60),
    ]


async def test_auth_budgets_are_independent_of_ip_checks_and_each_other(
    api: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    client, evaluate = api
    credentials = {"email": " Reader@Example.TEST ", "password": "dummy"}
    confirmation = {"email": credentials["email"], "token": "Abc123"}
    other_ip = {"X-Forwarded-For": OTHER_IP}
    evaluate.side_effect = [0, 9, 0, 0, 0, 0, 0, 7]

    assert (await client.post(LOGIN, json=credentials)).status_code == 429
    assert (await client.post(LOGIN, json=credentials, headers=other_ip)).status_code == 401
    assert (await client.post(CONFIRM, json=confirmation)).status_code == 401
    blocked = await client.post(CONFIRM, json=confirmation, headers=other_ip)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "7"

    email = "reader@example.test"
    assert [call.args[1:] for call in evaluate.await_args_list] == [
        (2, f"{PREFIX}api:ip:{IP}", f"{PREFIX}login:ip:{IP}", 60, 60, 60, 10),
        (1, f"{PREFIX}login:account_ip:{len(email)}:{email}:{IP}", 900, 10),
        (2, f"{PREFIX}api:ip:{OTHER_IP}", f"{PREFIX}login:ip:{OTHER_IP}", 60, 60, 60, 10),
        (1, f"{PREFIX}login:account_ip:{len(email)}:{email}:{OTHER_IP}", 900, 10),
        (2, f"{PREFIX}api:ip:{IP}", f"{PREFIX}confirmation:ip:{IP}", 60, 60, 900, 20),
        (1, f"{PREFIX}confirmation:email:{email}", 900, 5),
        (2, f"{PREFIX}api:ip:{OTHER_IP}", f"{PREFIX}confirmation:ip:{OTHER_IP}", 60, 60, 900, 20),
        (1, f"{PREFIX}confirmation:email:{email}", 900, 5),
    ]


async def test_password_reset_uses_its_own_ip_and_account_limits(
    api: tuple[httpx.AsyncClient, AsyncMock],
) -> None:
    client, evaluate = api
    reset = {"email": " Reader@Example.TEST ", "code": "Abc123", "new_password": "new-password"}
    evaluate.side_effect = [0, 0, 0, 19, 23, 0, 0]

    assert (await client.post(RESET_CONFIRM, json=reset)).status_code == 401
    email_blocked = await client.post(
        RESET_CONFIRM, json=reset, headers={"X-Forwarded-For": OTHER_IP}
    )
    assert email_blocked.status_code == 429
    assert email_blocked.headers["Retry-After"] == "19"
    ip_blocked = await client.post(RESET_CONFIRM, json={})
    assert ip_blocked.status_code == 429
    assert ip_blocked.headers["Retry-After"] == "23"
    assert (
        await client.post(CONFIRM, json={"email": reset["email"], "token": "Abc123"})
    ).status_code == 401

    email = "reader@example.test"
    assert [call.args[1:] for call in evaluate.await_args_list] == [
        (2, f"{PREFIX}api:ip:{IP}", f"{PREFIX}password_reset:ip:{IP}", 60, 60, 900, 20),
        (1, f"{PREFIX}password_reset:email:{email}", 900, 5),
        (2, f"{PREFIX}api:ip:{OTHER_IP}", f"{PREFIX}password_reset:ip:{OTHER_IP}", 60, 60, 900, 20),
        (1, f"{PREFIX}password_reset:email:{email}", 900, 5),
        (2, f"{PREFIX}api:ip:{IP}", f"{PREFIX}password_reset:ip:{IP}", 60, 60, 900, 20),
        (2, f"{PREFIX}api:ip:{IP}", f"{PREFIX}confirmation:ip:{IP}", 60, 60, 900, 20),
        (1, f"{PREFIX}confirmation:email:{email}", 900, 5),
    ]


@pytest.mark.parametrize("redis_available", [True, False])
async def test_middleware_limit_errors_use_common_handlers(
    api: tuple[httpx.AsyncClient, AsyncMock], redis_available: bool
) -> None:
    client, evaluate = api
    evaluate.return_value = 12
    if not redis_available:
        evaluate.side_effect = RedisConnectionError("private diagnostic")

    response = await client.post(LOGIN, json={"email": "reader@example.test", "password": "dummy"})

    evaluate.assert_awaited_once()
    assert response.headers["X-Request-ID"] == "rate-limit-test"
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Access-Control-Expose-Headers"] == "Retry-After"
    if redis_available:
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "12"
        assert response.json() == {"detail": "Too many requests"}
    else:
        assert response.status_code == 503
        assert response.json() == {"detail": "Rate limit service unavailable"}
