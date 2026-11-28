import asyncio
from uuid import UUID

from taskiq import AsyncBroker
from taskiq.exceptions import SendTaskError
from taskiq.kicker import AsyncKicker

from src.core.request_context import current_request_id
from src.modules.auth.errors import ConfirmationEnqueueError, PasswordResetEnqueueError

CONFIRMATION_TASK = "auth.send_confirmation"
PASSWORD_RESET_TASK = "auth.send_password_reset"


class TaskiqAuthMailQueue:
    def __init__(self, broker: AsyncBroker, timeout: float) -> None:
        self._broker = broker
        self._timeout = timeout

    async def enqueue(self, confirmation_id: UUID) -> None:
        try:
            await self._enqueue(CONFIRMATION_TASK, confirmation_id)
        except SendTaskError, TimeoutError:
            raise ConfirmationEnqueueError() from None

    async def enqueue_password_reset(self, reset_id: UUID) -> None:
        try:
            await self._enqueue(PASSWORD_RESET_TASK, reset_id)
        except SendTaskError, TimeoutError:
            raise PasswordResetEnqueueError() from None

    async def _enqueue(self, task_name: str, reservation_id: UUID) -> None:
        kicker: AsyncKicker[[str, str | None], None] = AsyncKicker(
            task_name, self._broker, {"ack_type": "manual"}
        )
        async with asyncio.timeout(self._timeout):
            await kicker.kiq(str(reservation_id), current_request_id())
