from datetime import UTC, datetime
from uuid import UUID

from pwdlib import PasswordHash

from src.core.uow import UnitOfWork
from src.modules.users import repository
from src.modules.users.domain import normalize_email
from src.modules.users.dto import CreateUserInput, UpdateProfileInput, UserState
from src.modules.users.errors import (
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidProfileError,
    UserNotFoundError,
)
from src.modules.users.models import User


class UsersService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow
        self._passwords = PasswordHash.recommended()

    async def create_user(self, data: CreateUserInput) -> UserState:
        """Raise EmailAlreadyExistsError for a duplicate normalized email."""
        user = User(
            email=data.email,
            password_hash=self._passwords.hash(data.password),
            email_confirmed=False,
            onboarding_completed=False,
            timezone=None,
            reminders_enabled=False,
            reminder_time=None,
            consent_version=data.consent_version,
            consent_accepted_at=datetime.now(UTC),
        )
        await repository.insert(self.uow.session, user)
        return self._state(user)

    async def verify_credentials(self, email: str, password: str) -> UserState:
        """Raise InvalidCredentialsError for invalid credentials."""
        try:
            email = normalize_email(email)
        except ValueError as exc:
            raise InvalidCredentialsError from exc
        user = await repository.find_by_email(self.uow.session, email)
        if user is None or not self._passwords.verify(password, user.password_hash):
            raise InvalidCredentialsError
        return self._state(user)

    async def get_account(self, user_id: UUID, *, for_update: bool = False) -> UserState:
        """Raise UserNotFoundError; for_update locks the stable account row."""
        return self._state(await self._get(user_id, for_update=for_update))

    async def confirm_email(self, user_id: UUID) -> UserState:
        """Idempotently confirm email; raise UserNotFoundError if absent."""
        user = await self._get(user_id, for_update=True)
        user.email_confirmed = True
        await repository.flush(self.uow.session)
        return self._state(user)

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        """Raise UserNotFoundError, InvalidCredentialsError, or InvalidPasswordError."""
        if len(new_password) < 8:
            raise InvalidPasswordError
        user = await self._get(user_id, for_update=True)
        if not self._passwords.verify(current_password, user.password_hash):
            raise InvalidCredentialsError
        user.password_hash = self._passwords.hash(new_password)
        await repository.flush(self.uow.session)

    async def update_profile(self, user_id: UUID, data: UpdateProfileInput) -> UserState:
        """Raise UserNotFoundError or InvalidProfileError."""
        user = await self._get(user_id, for_update=True)
        if "timezone" in data.model_fields_set:
            user.timezone = data.timezone
        if "reminder_time" in data.model_fields_set:
            if data.reminder_time is not None and data.reminder_time.tzinfo is not None:
                raise InvalidProfileError
            user.reminder_time = data.reminder_time
        if "reminders_enabled" in data.model_fields_set:
            if data.reminders_enabled is None:
                raise InvalidProfileError
            user.reminders_enabled = data.reminders_enabled
        if user.reminders_enabled and (user.timezone is None or user.reminder_time is None):
            raise InvalidProfileError
        await repository.flush(self.uow.session)
        return self._state(user)

    async def complete_onboarding(self, user_id: UUID) -> UserState:
        """Idempotent; raise UserNotFoundError if absent."""
        user = await self._get(user_id, for_update=True)
        user.onboarding_completed = True
        await repository.flush(self.uow.session)
        return self._state(user)

    async def _get(self, user_id: UUID, *, for_update: bool = False) -> User:
        user = await repository.find_by_id(self.uow.session, user_id, for_update=for_update)
        if user is None:
            raise UserNotFoundError
        return user

    @staticmethod
    def _state(user: User) -> UserState:
        return UserState.model_validate(user, from_attributes=True)
