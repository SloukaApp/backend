import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.modules.mail.adapters import MailSender, SmtpDeliveryError
from src.modules.mail.dto import CodeEmail

logger = logging.getLogger(__name__)


class MailService:
    def __init__(self, sender: MailSender, max_retries: int) -> None:
        self._sender = sender
        self._max_retries = max_retries

    async def send_confirmation(
        self, message: CodeEmail, *, can_retry: Callable[[], Awaitable[bool]]
    ) -> None:
        await self._send_code(
            message,
            subject="Confirm your Slouka email",
            heading="Your Slouka verification code",
            instructions="Enter this code in the Slouka app to confirm your email address.",
            can_retry=can_retry,
        )

    async def send_password_reset(
        self, message: CodeEmail, *, can_retry: Callable[[], Awaitable[bool]]
    ) -> None:
        await self._send_code(
            message,
            subject="Reset your Slouka password",
            heading="Your Slouka password reset code",
            instructions="Enter this code in the Slouka app to set a new password.",
            can_retry=can_retry,
        )

    async def _send_code(
        self,
        message: CodeEmail,
        *,
        subject: str,
        heading: str,
        instructions: str,
        can_retry: Callable[[], Awaitable[bool]],
    ) -> None:
        ttl_minutes = (message.expires_at - message.created_at).total_seconds() / 60
        text = (
            f"{heading}:\n\n{message.code}\n\n{instructions} "
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
                    subject=subject,
                    text=text,
                    message_id=message.message_id,
                    date=message.created_at,
                    timeout_budget=remaining,
                )
            except SmtpDeliveryError:
                if attempt == self._max_retries:
                    logger.warning(
                        "Auth email delivery attempts exhausted", extra={"subject": subject}
                    )
                    return
                await asyncio.sleep(0.25 * (attempt + 1))
            else:
                return
