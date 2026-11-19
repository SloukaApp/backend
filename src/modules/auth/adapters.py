import asyncio
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Protocol
from uuid import UUID

import aiosmtplib
import jwt
from jwt.exceptions import InvalidTokenError

from src.core.config import SmtpConfig
from src.modules.auth.errors import InvalidAccessError, MailDeliveryError


class ConfirmationMailer(Protocol):
    async def send_confirmation(self, email: str, token: str) -> None: ...


class SmtpConfirmationMailer:
    """Bounded SMTP delivery. Every attempt closes its own connection."""

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config
        self._closed = False

    async def close(self) -> None:
        self._closed = True

    async def send_confirmation(self, email: str, token: str) -> None:
        if self._closed:
            raise MailDeliveryError()
        message = EmailMessage()
        message["From"] = self._config.from_email
        message["To"] = email
        message["Subject"] = "Confirm your Slouka email"
        message["Date"] = formatdate(usegmt=True)
        sender_domain = parseaddr(self._config.from_email)[1].rpartition("@")[2]
        message["Message-ID"] = make_msgid(domain=sender_domain or None)
        message.set_content(
            f"Your Slouka verification code:\n\n{token}\n\n"
            "Enter this code in the Slouka app to confirm your email address. "
            "The code is valid for 15 minutes, is case-sensitive, and can be used once.\n\n"
            "If you did not request this code, you can ignore this email.\n"
        )
        for attempt in range(self._config.max_retries + 1):
            smtp = aiosmtplib.SMTP(
                hostname=self._config.host,
                port=self._config.port,
                timeout=self._config.timeout_seconds,
                use_tls=self._config.use_tls,
                start_tls=self._config.start_tls,
                username=self._config.user,
                password=self._config.password.get_secret_value()
                if self._config.password
                else None,
            )
            try:
                await smtp.connect()
                await smtp.send_message(message)
                return
            except aiosmtplib.SMTPException, OSError, TimeoutError:
                if attempt == self._config.max_retries:
                    raise MailDeliveryError() from None
            finally:
                smtp.close()
            await asyncio.sleep(0.25 * (attempt + 1))


def decode_access(token: str, secret: str) -> tuple[UUID, UUID]:
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "device_id", "iat", "exp", "type"]},
        )
        if claims["type"] != "access":
            raise InvalidAccessError()
        return UUID(claims["sub"]), UUID(claims["device_id"])
    except (InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        raise InvalidAccessError() from exc
