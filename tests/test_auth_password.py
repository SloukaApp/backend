from collections.abc import AsyncIterator
from datetime import datetime
from os import getenv
from secrets import token_urlsafe
from uuid import UUID, uuid7

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src import main
from src.core.config import Settings, get_settings
from src.core.uow import UnitOfWork
from src.modules.auth import repository
from src.modules.auth.dependencies import check_login
from src.modules.auth.models import Device, RefreshToken
from src.modules.auth.schemas import TokenResponse
from src.modules.users.dto import CreateUserInput
from src.modules.users.models import User
from src.modules.users.service import UsersService

OLD_PASSWORD = "old-password"
NEW_PASSWORD = "newPass!"


@pytest.fixture
async def password_api(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    dsn = getenv("TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("TEST_DATABASE_DSN must point to a migrated test PostgreSQL database")

    settings = Settings.model_validate(
        {
            "db": {"dsn": dsn},
            "redis": {"dsn": "redis://localhost:6379"},
            "auth": {"jwt_secret": token_urlsafe(48)},
            "smtp": {"host": "localhost", "from_email": "noreply@example.test"},
        }
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[check_login] = lambda: None
    email = f"password-test-{uuid7()}@example.test"
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver/api/v1/auth/") as client,
    ):
        sessions = app.state.session_factory
        uow = UnitOfWork(sessions)
        users = UsersService(uow)
        async with uow:
            account = await users.create_user(
                CreateUserInput(
                    email=email, password=OLD_PASSWORD, consent=True, consent_version="test"
                )
            )
            await users.confirm_email(account.id)

        try:
            yield client, email
        finally:
            async with sessions.begin() as session:
                device_ids = select(Device.id).where(Device.user_id == account.id)
                await session.execute(
                    delete(RefreshToken).where(RefreshToken.device_id.in_(device_ids))
                )
                await session.execute(delete(Device).where(Device.user_id == account.id))
                await session.execute(delete(User).where(User.id == account.id))


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("login", json={"email": email, "password": password})


async def authorize(client: httpx.AsyncClient, email: str) -> TokenResponse:
    response = await login(client, email, OLD_PASSWORD)
    assert response.status_code == 200
    return TokenResponse.model_validate_json(response.content)


async def refresh(client: httpx.AsyncClient, tokens: TokenResponse) -> httpx.Response:
    return await client.post("refresh", json={"refresh_token": tokens.refresh_token})


async def change_password(
    client: httpx.AsyncClient, tokens: TokenResponse, current_password: str, new_password: str
) -> httpx.Response:
    return await client.post(
        "password",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
        json={"current_password": current_password, "new_password": new_password},
    )


async def test_password_change_updates_login_and_revokes_all_refresh_tokens(
    password_api: tuple[httpx.AsyncClient, str],
) -> None:
    client, email = password_api
    first_device = await authorize(client, email)
    second_device = await authorize(client, email)
    assert first_device.refresh_token != second_device.refresh_token

    response = await change_password(client, first_device, OLD_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 204
    assert response.content == b""
    assert (await login(client, email, OLD_PASSWORD)).status_code == 401
    assert (await login(client, email, NEW_PASSWORD)).status_code == 200
    assert (await refresh(client, first_device)).status_code == 401
    assert (await refresh(client, second_device)).status_code == 401


@pytest.mark.parametrize(
    ("current_password", "new_password", "expected_status"),
    [
        pytest.param("wrong-password", NEW_PASSWORD, 401, id="wrong-current-password"),
        pytest.param(OLD_PASSWORD, "abc123!", 422, id="short-new-password"),
    ],
)
async def test_rejected_password_change_preserves_credentials(
    password_api: tuple[httpx.AsyncClient, str],
    current_password: str,
    new_password: str,
    expected_status: int,
) -> None:
    client, email = password_api
    device = await authorize(client, email)

    response = await change_password(client, device, current_password, new_password)

    assert response.status_code == expected_status
    assert (await login(client, email, OLD_PASSWORD)).status_code == 200
    assert (await login(client, email, new_password)).status_code == 401
    assert (await refresh(client, device)).status_code == 200


async def test_password_change_rolls_back_password_and_token_revocations(
    password_api: tuple[httpx.AsyncClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, email = password_api
    first_device = await authorize(client, email)
    second_device = await authorize(client, email)
    revoke_all = repository.revoke_all
    wrote_revocations = False

    async def fail_after_revocation(session: AsyncSession, user_id: UUID, now: datetime) -> None:
        nonlocal wrote_revocations
        await revoke_all(session, user_id, now)
        wrote_revocations = True
        raise RuntimeError("Simulated failure before commit")

    monkeypatch.setattr(repository, "revoke_all", fail_after_revocation)
    response = await change_password(client, first_device, OLD_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 500
    assert wrote_revocations
    assert (await login(client, email, OLD_PASSWORD)).status_code == 200
    assert (await login(client, email, NEW_PASSWORD)).status_code == 401
    assert (await refresh(client, first_device)).status_code == 200
    assert (await refresh(client, second_device)).status_code == 200
