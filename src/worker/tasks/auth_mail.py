from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from src.core.uow import UnitOfWork
from src.modules.auth.dto import ConfirmationDelivery, PasswordResetDelivery
from src.modules.auth.service import AuthService
from src.modules.mail.dto import CodeEmail
from src.modules.mail.service import MailService


class SendCode(Protocol):
    async def __call__(
        self, message: CodeEmail, *, can_retry: Callable[[], Awaitable[bool]]
    ) -> None: ...


async def deliver_confirmation(
    confirmation_id: UUID, uow: UnitOfWork, auth: AuthService, mail: MailService
) -> None:
    await _deliver_code(
        confirmation_id,
        uow,
        auth.prepare_confirmation_delivery,
        auth.confirmation_delivery_is_current,
        mail.send_confirmation,
    )


async def deliver_password_reset(
    reset_id: UUID, uow: UnitOfWork, auth: AuthService, mail: MailService
) -> None:
    await _deliver_code(
        reset_id,
        uow,
        auth.prepare_password_reset_delivery,
        auth.password_reset_delivery_is_current,
        mail.send_password_reset,
    )


async def _deliver_code(
    reservation_id: UUID,
    uow: UnitOfWork,
    prepare: Callable[[UUID], Awaitable[ConfirmationDelivery | PasswordResetDelivery | None]],
    is_current: Callable[[UUID], Awaitable[bool]],
    send: SendCode,
) -> None:
    async with uow:
        delivery = await prepare(reservation_id)
    if delivery is None:
        return

    async def can_retry() -> bool:
        async with uow:
            return await is_current(reservation_id)

    await send(
        CodeEmail(
            message_id=reservation_id,
            email=delivery.email,
            code=delivery.code,
            created_at=delivery.created_at,
            expires_at=delivery.expires_at,
        ),
        can_retry=can_retry,
    )
