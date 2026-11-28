import asyncio
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from typing import Protocol
from uuid import UUID

import aiosmtplib

from src.core.config import SmtpConfig


class SmtpDeliveryError(Exception):
    pass


class MailSender(Protocol):
    async def send(
        self,
        *,
        email: str,
        subject: str,
        text: str,
        message_id: UUID,
        date: datetime,
        timeout_budget: float,
    ) -> None: ...


class SmtpMailer:
    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    async def send(
        self,
        *,
        email: str,
        subject: str,
        text: str,
        message_id: UUID,
        date: datetime,
        timeout_budget: float,
    ) -> None:
        message = EmailMessage()
        message["From"] = self._config.from_email
        message["To"] = email
        message["Subject"] = subject
        message["Date"] = format_datetime(date, usegmt=True)
        sender_domain = parseaddr(self._config.from_email)[1].rpartition("@")[2]
        message["Message-ID"] = f"<{message_id.hex}@{sender_domain}>"
        message.set_content(text)

        timeout = min(self._config.timeout_seconds, timeout_budget)
        smtp = aiosmtplib.SMTP(
            hostname=self._config.host,
            port=self._config.port,
            timeout=timeout,
            use_tls=self._config.use_tls,
            start_tls=self._config.start_tls,
            username=self._config.user,
            password=self._config.password.get_secret_value() if self._config.password else None,
        )
        try:
            async with asyncio.timeout(timeout):
                await smtp.connect()
                await smtp.send_message(message)
        except aiosmtplib.SMTPException, OSError, TimeoutError:
            raise SmtpDeliveryError() from None
        finally:
            smtp.close()
