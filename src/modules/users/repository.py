from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.errors import EmailAlreadyExistsError, InvalidProfileError
from src.modules.users.models import User


async def find_by_id(
    session: AsyncSession, user_id: UUID, *, for_update: bool = False
) -> User | None:
    statement = select(User).where(User.id == user_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(statement)


async def find_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        original = exc.orig
        cause = getattr(original, "__cause__", None)
        state = getattr(original, "sqlstate", None)
        constraint = getattr(cause, "constraint_name", None)
        if state == "23505" and constraint == "uq_users_email":
            raise EmailAlreadyExistsError from exc
        if state == "23514" and constraint == "ck_users_reminder_configuration":
            raise InvalidProfileError from exc
        raise


async def insert(session: AsyncSession, user: User) -> None:
    session.add(user)
    await flush(session)
