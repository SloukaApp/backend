from uuid import UUID

from src.core.uow import UnitOfWork
from src.modules.auth.service import AuthService
from src.modules.mail.dto import ConfirmationEmail
from src.modules.mail.service import MailService


async def deliver_confirmation(
    confirmation_id: UUID, uow: UnitOfWork, auth: AuthService, mail: MailService
) -> None:
    async with uow:
        delivery = await auth.prepare_confirmation_delivery(confirmation_id)
    if delivery is None:
        return

    async def can_retry() -> bool:
        async with uow:
            return await auth.confirmation_delivery_is_current(confirmation_id)

    await mail.send_confirmation(
        ConfirmationEmail(
            message_id=confirmation_id,
            email=delivery.email,
            code=delivery.code,
            created_at=delivery.created_at,
            expires_at=delivery.expires_at,
        ),
        can_retry=can_retry,
    )
