from typing import Protocol
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError

from src.modules.auth.errors import InvalidAccessError


class ConfirmationQueue(Protocol):
    async def enqueue(self, confirmation_id: UUID) -> None: ...


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
