import asyncio
from uuid import UUID

from taskiq import AsyncBroker
from taskiq.exceptions import SendTaskError
from taskiq.kicker import AsyncKicker

from src.core.request_context import current_request_id
from src.modules.auth.errors import ConfirmationEnqueueError

CONFIRMATION_TASK = "auth.send_confirmation"


class TaskiqConfirmationQueue:
    def __init__(self, broker: AsyncBroker, timeout: float) -> None:
        self._broker = broker
        self._timeout = timeout

    async def enqueue(self, confirmation_id: UUID) -> None:
        kicker: AsyncKicker[[str, str | None], None] = AsyncKicker(
            CONFIRMATION_TASK, self._broker, {"ack_type": "manual"}
        )
        try:
            async with asyncio.timeout(self._timeout):
                await kicker.kiq(str(confirmation_id), current_request_id())
        except SendTaskError, TimeoutError:
            raise ConfirmationEnqueueError() from None
