import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import getenv
from secrets import token_urlsafe
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import httpx
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from taskiq.exceptions import SendTaskError
from taskiq.kicker import AsyncKicker

from src import main
from src.core.config import Settings, get_settings
from src.core.uow import UnitOfWork
from src.modules.auth.models import Device, PasswordReset, RefreshToken
from src.modules.auth.schemas import TokenResponse
from src.modules.auth.service import AuthService
from src.modules.mail.service import MailService
from src.modules.users.dto import CreateUserInput
from src.modules.users.models import User
from src.modules.users.service import UsersService
from src.worker.queue import PASSWORD_RESET_TASK
from src.worker.tasks.auth_mail import deliver_password_reset

OLD_PASSWORD = "original-password"
NEW_PASSWORD = "replacement-password"
REQUEST_RESET = "password-reset/request"
CONFIRM_RESET = "password-reset/confirm"


@dataclass(frozen=True)
class ResetAPI:
    client: httpx.AsyncClient
    confirmed_email: str
    unconfirmed_email: str
    sessions: async_sessionmaker[AsyncSession]
    settings: Settings
    deliveries: list[UUID]

    async def request_reset(self) -> UUID:
        response = await self.client.post(REQUEST_RESET, json={"email": self.confirmed_email})
        assert response.status_code == 202
        return self.deliveries[-1]

    async def deliver_code(self, reservation_id: UUID) -> str | None:
        uow = UnitOfWork(self.sessions)
        auth = AuthService(uow, UsersService(uow), self.settings.auth)
        sender = AsyncMock()
        await deliver_password_reset(reservation_id, uow, auth, MailService(sender, max_retries=0))
        if not sender.send.await_count:
            return None
        sender.send.assert_awaited_once()
        message = sender.send.await_args.kwargs
        assert message["email"] == self.confirmed_email
        assert message["subject"] == "Reset your Slouka password"
        assert message["message_id"] == reservation_id
        match = re.search(r"\n\n([A-Za-z0-9]{6})\n\n", message["text"])
        assert match is not None
        return match[1]

    async def confirm(self, code: str, password: str = NEW_PASSWORD) -> httpx.Response:
        return await self.client.post(
            CONFIRM_RESET,
            json={"email": self.confirmed_email, "code": code, "new_password": password},
        )

    async def login(self, password: str = OLD_PASSWORD) -> httpx.Response:
        return await self.client.post(
            "login", json={"email": self.confirmed_email, "password": password}
        )


@pytest.fixture
async def reset_api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[ResetAPI]:
    dsn = getenv("TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("TEST_DATABASE_DSN must point to a migrated test PostgreSQL database")

    settings = Settings.model_validate(
        {
            "db": {"dsn": dsn},
            "redis": {"dsn": "redis://localhost:6379"},
            "auth": {
                "jwt_secret": token_urlsafe(48),
                "confirmation_secret": token_urlsafe(32),
            },
        }
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    confirmed_email = f"reset-confirmed-{uuid7()}@example.test"
    unconfirmed_email = f"reset-unconfirmed-{uuid7()}@example.test"
    deliveries: list[UUID] = []

    async def enqueue(self: AsyncKicker, reservation_id: str, request_id: str | None) -> None:
        assert self.task_name == PASSWORD_RESET_TASK
        deliveries.append(UUID(reservation_id))

    monkeypatch.setattr(AsyncKicker, "kiq", enqueue)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver/api/v1/auth/") as client,
    ):
        monkeypatch.setattr(app.state.redis, "eval", AsyncMock(return_value=0))
        sessions = app.state.session_factory
        uow = UnitOfWork(sessions)
        users = UsersService(uow)
        async with uow:
            for email in (confirmed_email, unconfirmed_email):
                account = await users.create_user(
                    CreateUserInput(
                        email=email, password=OLD_PASSWORD, consent=True, consent_version="test"
                    )
                )
                if email == confirmed_email:
                    await users.confirm_email(account.id)

        try:
            yield ResetAPI(
                client, confirmed_email, unconfirmed_email, sessions, settings, deliveries
            )
        finally:
            async with sessions.begin() as session:
                accounts = User.email.in_((confirmed_email, unconfirmed_email))
                user_ids = select(User.id).where(accounts)
                devices = Device.user_id.in_(user_ids)
                device_ids = select(Device.id).where(devices)
                await session.execute(
                    delete(RefreshToken).where(RefreshToken.device_id.in_(device_ids))
                )
                await session.execute(delete(Device).where(devices))
                await session.execute(
                    delete(PasswordReset).where(PasswordReset.user_id.in_(user_ids))
                )
                await session.execute(delete(User).where(accounts))


async def test_reset_is_atomic_and_one_time_across_concurrent_requests(reset_api: ResetAPI) -> None:
    first_device = TokenResponse.model_validate((await reset_api.login()).json())
    second_device = TokenResponse.model_validate((await reset_api.login()).json())
    assert first_device.refresh_token != second_device.refresh_token

    reservation_id = await reset_api.request_reset()
    code = await reset_api.deliver_code(reservation_id)
    assert code is not None
    assert await reset_api.deliver_code(reservation_id) == code

    responses = await asyncio.gather(reset_api.confirm(code), reset_api.confirm(code))
    assert sorted(response.status_code for response in responses) == [204, 401]
    replay = await reset_api.confirm(code)
    assert replay.status_code == 401
    assert replay.json() == {"detail": "Invalid password reset code"}
    assert await reset_api.deliver_code(reservation_id) is None
    assert (await reset_api.login()).status_code == 401
    assert (await reset_api.login(NEW_PASSWORD)).status_code == 200
    for token in (first_device, second_device):
        response = await reset_api.client.post(
            "refresh", json={"refresh_token": token.refresh_token}
        )
        assert response.status_code == 401


@pytest.mark.parametrize("expired", [False, True], ids=["wrong-code", "expired-code"])
async def test_invalid_reset_keeps_existing_password(reset_api: ResetAPI, expired: bool) -> None:
    reservation_id = await reset_api.request_reset()
    delivered = await reset_api.deliver_code(reservation_id)
    assert delivered is not None
    if expired:
        expires_at = datetime.now(UTC) - timedelta(seconds=1)
        async with reset_api.sessions.begin() as session:
            await session.execute(
                update(PasswordReset)
                .where(PasswordReset.id == reservation_id)
                .values(created_at=expires_at - timedelta(minutes=15), expires_at=expires_at)
            )
        assert await reset_api.deliver_code(reservation_id) is None
        code = delivered
    else:
        code = ("B" if delivered[0] == "A" else "A") + delivered[1:]

    response = await reset_api.confirm(code)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid password reset code"}
    assert (await reset_api.login()).status_code == 200
    assert (await reset_api.login(NEW_PASSWORD)).status_code == 401


async def test_reset_request_is_uniform_and_respects_cooldown(reset_api: ResetAPI) -> None:
    addresses = (
        reset_api.confirmed_email,
        reset_api.unconfirmed_email,
        "unknown@example.test",
        reset_api.confirmed_email.upper(),
    )
    responses = [await reset_api.client.post(REQUEST_RESET, json={"email": e}) for e in addresses]
    assert {response.status_code for response in responses} == {202}
    assert len({response.content for response in responses}) == 1
    first, unconfirmed, unknown, cooldown = reset_api.deliveries
    code = await reset_api.deliver_code(first)
    assert code is not None
    for reservation_id in (unconfirmed, unknown, cooldown):
        assert await reset_api.deliver_code(reservation_id) is None

    expired_cooldown = datetime.now(UTC) - timedelta(seconds=61)
    async with reset_api.sessions.begin() as session:
        await session.execute(
            update(PasswordReset)
            .where(PasswordReset.id == first)
            .values(created_at=expired_cooldown)
        )
    replacement = await reset_api.request_reset()
    assert await reset_api.deliver_code(first) is None
    replacement_code = await reset_api.deliver_code(replacement)
    assert replacement_code is not None
    assert (await reset_api.confirm(code)).status_code == 401
    assert (await reset_api.confirm(replacement_code)).status_code == 204


async def test_reset_queue_failure_has_a_uniform_response(
    reset_api: ResetAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueue = AsyncMock(side_effect=SendTaskError)
    monkeypatch.setattr(AsyncKicker, "kiq", enqueue)
    addresses = (reset_api.confirmed_email, reset_api.unconfirmed_email, "unknown@example.test")
    responses = [await reset_api.client.post(REQUEST_RESET, json={"email": e}) for e in addresses]
    assert enqueue.await_count == len(addresses)
    assert {response.status_code for response in responses} == {503}
    assert len({response.content for response in responses}) == 1
