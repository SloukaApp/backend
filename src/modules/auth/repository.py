from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.errors import AuthorizationConflictError
from src.modules.auth.models import Device, EmailConfirmation, RefreshToken
from src.modules.users.errors import UserNotFoundError


async def add_confirmation(session: AsyncSession, confirmation: EmailConfirmation) -> None:
    session.add(confirmation)
    await flush(session)


async def get_confirmation(
    session: AsyncSession, user_id: UUID, digest: str
) -> EmailConfirmation | None:
    return await session.scalar(
        select(EmailConfirmation)
        .where(EmailConfirmation.user_id == user_id, EmailConfirmation.token_hash == digest)
        .with_for_update()
    )


async def latest_confirmation(session: AsyncSession, user_id: UUID) -> EmailConfirmation | None:
    return await session.scalar(
        select(EmailConfirmation)
        .where(EmailConfirmation.user_id == user_id)
        .order_by(EmailConfirmation.created_at.desc())
        .limit(1)
    )


async def revoke_confirmations(session: AsyncSession, user_id: UUID, now: datetime) -> None:
    await session.execute(
        update(EmailConfirmation)
        .where(
            EmailConfirmation.user_id == user_id,
            EmailConfirmation.consumed_at.is_(None),
            EmailConfirmation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


async def get_device(session: AsyncSession, user_id: UUID, installation_id: UUID) -> Device | None:
    return await session.scalar(
        select(Device).where(Device.user_id == user_id, Device.installation_id == installation_id)
    )


async def get_owned_device(session: AsyncSession, user_id: UUID, device_id: UUID) -> Device | None:
    return await session.scalar(
        select(Device).where(Device.user_id == user_id, Device.id == device_id)
    )


async def active_device_count(session: AsyncSession, user_id: UUID, now: datetime) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Device)
            .join(RefreshToken, RefreshToken.device_id == Device.id)
            .where(
                Device.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        or 0
    )


async def current_refresh(session: AsyncSession, device_id: UUID) -> RefreshToken | None:
    return await session.scalar(
        select(RefreshToken).where(
            RefreshToken.device_id == device_id, RefreshToken.revoked_at.is_(None)
        )
    )


async def refresh_owner(session: AsyncSession, digest: str) -> UUID | None:
    return await session.scalar(
        select(Device.user_id)
        .join(RefreshToken, RefreshToken.device_id == Device.id)
        .where(RefreshToken.token_hash == digest)
    )


async def get_refresh(session: AsyncSession, digest: str) -> RefreshToken | None:
    return await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == digest).with_for_update()
    )


async def save_device(session: AsyncSession, device: Device) -> None:
    session.add(device)
    await flush(session)


async def add_refresh(session: AsyncSession, refresh: RefreshToken) -> None:
    session.add(refresh)
    await flush(session)


async def flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        state = getattr(exc.orig, "sqlstate", None)
        constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
        if state == "23505" and constraint in {
            "uq_devices_user_installation",
            "uq_refresh_tokens_current_device",
            "uq_refresh_tokens_token_hash",
            "uq_email_confirmations_current_user",
            "uq_email_confirmations_token_hash",
        }:
            raise AuthorizationConflictError() from exc
        if state == "23503" and constraint in {
            "fk_devices_user_id_users",
            "fk_email_confirmations_user_id_users",
        }:
            raise UserNotFoundError() from exc
        if state == "23503" and constraint == "fk_refresh_tokens_device_id_devices":
            raise AuthorizationConflictError() from exc
        if state == "23514" and constraint in {
            "ck_refresh_tokens_refresh_expiry",
            "ck_email_confirmations_confirmation_expiry",
        }:
            raise AuthorizationConflictError() from exc
        raise


async def revoke_device(session: AsyncSession, device_id: UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.device_id == device_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke_all(session: AsyncSession, user_id: UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.device_id.in_(select(Device.id).where(Device.user_id == user_id)),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )


async def list_devices(
    session: AsyncSession, user_id: UUID, now: datetime, limit: int, offset: int
) -> tuple[list[tuple[Device, bool]], int]:
    active = (
        select(RefreshToken.id)
        .where(
            RefreshToken.device_id == Device.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        .exists()
    )
    result = await session.execute(
        select(Device, active)
        .where(Device.user_id == user_id)
        .order_by(Device.created_at.desc(), Device.id.desc())
        .limit(limit)
        .offset(offset)
    )
    total = int(
        await session.scalar(
            select(func.count()).select_from(Device).where(Device.user_id == user_id)
        )
        or 0
    )
    return [(row[0], bool(row[1])) for row in result], total
