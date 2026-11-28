from os import getenv
from secrets import token_urlsafe
from uuid import uuid7

import pytest
from sqlalchemy import delete, select

from src.core.config import AuthConfig, PostgresConfig
from src.core.db import build_engine, build_session_factory
from src.core.uow import UnitOfWork
from src.modules.auth.errors import InvalidConfirmationError
from src.modules.auth.models import Device, EmailConfirmation, RefreshToken
from src.modules.auth.service import AuthService
from src.modules.users.dto import CreateUserInput
from src.modules.users.models import User
from src.modules.users.service import UsersService


async def test_confirmation_can_be_redelivered_and_consumed_once() -> None:
    dsn = getenv("TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("TEST_DATABASE_DSN must point to a migrated test PostgreSQL database")

    engine = build_engine(PostgresConfig.model_validate({"dsn": dsn}))
    sessions = build_session_factory(engine)
    config = AuthConfig.model_validate(
        {
            "jwt_secret": token_urlsafe(48),
            "confirmation_secret": token_urlsafe(32),
            "confirmation_resend_cooldown_seconds": 0,
        }
    )
    email = f"confirmation-test-{uuid7()}@example.test"
    password = token_urlsafe(16)

    def auth_operation() -> tuple[UnitOfWork, AuthService]:
        uow = UnitOfWork(sessions)
        return uow, AuthService(uow, UsersService(uow), config)

    try:
        api_uow, api = auth_operation()
        async with api_uow:
            original_id = await api.register(
                CreateUserInput(
                    email=email, password=password, consent=True, consent_version="test"
                )
            )

        worker_uow, worker = auth_operation()
        async with worker_uow:
            original = await worker.prepare_confirmation_delivery(original_id)
            assert original is not None

        restarted_uow, restarted_worker = auth_operation()
        async with restarted_uow:
            assert await restarted_worker.prepare_confirmation_delivery(original_id) == original

        async with api_uow:
            replacement_id = await api.resend_confirmation(email, password)
        async with restarted_uow:
            assert await restarted_worker.prepare_confirmation_delivery(original_id) is None
            replacement = await restarted_worker.prepare_confirmation_delivery(replacement_id)
            assert replacement is not None

        async with api_uow:
            await api.confirm_email(email, replacement.code)
        with pytest.raises(InvalidConfirmationError):
            async with api_uow:
                await api.confirm_email(email, replacement.code)
        async with restarted_uow:
            assert await restarted_worker.prepare_confirmation_delivery(replacement_id) is None
    finally:
        try:
            async with sessions.begin() as session:
                user_ids = select(User.id).where(User.email == email)
                device_ids = select(Device.id).where(Device.user_id.in_(user_ids))
                await session.execute(
                    delete(RefreshToken).where(RefreshToken.device_id.in_(device_ids))
                )
                await session.execute(delete(Device).where(Device.user_id.in_(user_ids)))
                await session.execute(
                    delete(EmailConfirmation).where(EmailConfirmation.user_id.in_(user_ids))
                )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
        finally:
            await engine.dispose()
