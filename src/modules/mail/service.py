import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.modules.mail.adapters import MailSender, SmtpDeliveryError
from src.modules.mail.dto import ConfirmationEmail

logger = logging.getLogger(__name__)


class MailService:
    def __init__(self, sender: MailSender, max_retries: int) -> None:
        self._sender = sender
        self._max_retries = max_retries

    async def send_confirmation(
        self, message: ConfirmationEmail, *, can_retry: Callable[[], Awaitable[bool]]
    ) -> None:
        """Send an issued code, checking its validity before each retry."""
        ttl_minutes = (message.expires_at - message.created_at).total_seconds() / 60
        text = (
            f"Your Slouka verification code:\n\n{message.code}\n\n"
            "Enter this code in the Slouka app to confirm your email address. "
            f"The code is valid for {ttl_minutes:g} minutes after you request it, "
            "is case-sensitive, and can be used once.\n\n"
            "If you did not request this code, you can ignore this email.\n"
        )
        for attempt in range(self._max_retries + 1):
            if attempt and not await can_retry():
                return
            remaining = (message.expires_at - datetime.now(UTC)).total_seconds()
            if remaining <= 0:
                return
            try:
                await self._sender.send(
                    email=message.email,
                    subject="Confirm your Slouka email",
                    text=text,
                    message_id=message.message_id,
                    date=message.created_at,
                    timeout_budget=remaining,
                )
            except SmtpDeliveryError:
                if attempt == self._max_retries:
                    logger.warning("Confirmation email delivery attempts exhausted")
                    return
                await asyncio.sleep(0.25 * (attempt + 1))
            else:
                return
