import re
from email.errors import HeaderParseError
from email.headerregistry import Address
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def normalize_email(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or any(char.isspace() for char in value):
        raise ValueError("Invalid email address")
    try:
        parsed = Address(addr_spec=value)
        domain = parsed.domain.encode("idna").decode("ascii").lower()
    except (ValueError, UnicodeError, HeaderParseError) as exc:
        raise ValueError("Invalid email address") from exc
    labels = domain.split(".")
    if (
        not parsed.username
        or len(parsed.username.encode("utf-8")) > 64
        or len(labels) < 2
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
    ):
        raise ValueError("Invalid email address")
    normalized = Address(username=parsed.username.lower(), domain=domain).addr_spec
    if len(normalized.encode("utf-8")) > 254:
        raise ValueError("Invalid email address")
    return normalized


def validate_timezone(value: str | None) -> str | None:
    if value is not None:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Invalid IANA timezone") from exc
    return value
