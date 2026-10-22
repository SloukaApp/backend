import hashlib
import secrets
import string
from datetime import datetime, timedelta
from uuid import UUID

import jwt


def random_token() -> str:
    return secrets.token_urlsafe(48)


def confirmation_token() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


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
