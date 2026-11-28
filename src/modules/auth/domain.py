import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta
from uuid import UUID

import jwt


def random_token() -> str:
    return secrets.token_urlsafe(48)


def confirmation_token(confirmation_id: UUID, secret: str) -> str:
    alphabet = string.ascii_letters + string.digits
    digest = hmac.digest(secret.encode(), confirmation_id.bytes, "sha256")
    value = int.from_bytes(digest, "big")
    characters: list[str] = []
    for _ in range(6):
        value, index = divmod(value, len(alphabet))
        characters.append(alphabet[index])
    return "".join(reversed(characters))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def encode_access(user_id: UUID, device_id: UUID, secret: str, now: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "device_id": str(device_id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "type": "access",
        },
        secret,
        algorithm="HS256",
    )
