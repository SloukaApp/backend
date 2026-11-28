import logging
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from uuid import UUID

from src.core.config import AuthConfig
from src.core.uow import UnitOfWork
from src.modules.auth import repository
from src.modules.auth.adapters import decode_access
from src.modules.auth.domain import confirmation_token, encode_access, random_token, token_hash
from src.modules.auth.dto import (
    ConfirmationDelivery,
    DeviceInfo,
    DevicePage,
    Principal,
    TokenPair,
)
from src.modules.auth.errors import (
    ConfirmationConflictError,
    DeviceLimitError,
    DeviceNotFoundError,
    EmailUnconfirmedError,
    InvalidAccessError,
    InvalidConfirmationError,
    InvalidRefreshError,
)
from src.modules.auth.models import Device, EmailConfirmation, RefreshToken
from src.modules.users.dto import CreateUserInput, UserState
from src.modules.users.errors import InvalidCredentialsError, UserNotFoundError
from src.modules.users.service import UsersService

logger = logging.getLogger(__name__)


class AuthService:
    """Own auth workflows; dependency direction is auth → users. Shared operation UoW."""

    def __init__(
        self,
        uow: UnitOfWork,
        users: UsersService,
        config: AuthConfig,
    ) -> None:
        self.uow = uow
        self.users = users
        self.config = config

    async def authenticate(self, token: str) -> tuple[Principal, UserState]:
        """Raise InvalidAccessError for invalid JWT or absent account."""
        user_id, device_id = decode_access(token, self.config.jwt_secret.get_secret_value())
        account = await self._authenticated_account(user_id)
        return Principal(user_id=user_id, device_id=device_id), account

    async def _authenticated_account(self, user_id: UUID, *, for_update: bool = False) -> UserState:
        try:
            return await self.users.get_account(user_id, for_update=for_update)
        except UserNotFoundError as exc:
            raise InvalidAccessError() from exc

    async def login(self, email: str, password: str) -> TokenPair:
        """Raise InvalidCredentialsError, EmailUnconfirmedError, or DeviceLimitError."""
        try:
            account = await self.users.verify_credentials(email, password)
            account = await self.users.get_account(account.id, for_update=True)
            account = await self.users.verify_credentials(email, password)
        except InvalidCredentialsError:
            logger.warning("Login credentials rejected")
            raise
        if not account.email_confirmed:
            raise EmailUnconfirmedError()
        return await self._authorize(account.id, datetime.now(UTC))

    async def _authorize(self, user_id: UUID, now: datetime) -> TokenPair:
        count = await repository.active_device_count(self.uow.session, user_id, now)
        if count >= self.config.max_active_devices:
            raise DeviceLimitError()
        device = Device(user_id=user_id, created_at=now, last_authorized_at=now)
        return await self._issue(device, now)

    async def _issue(self, device: Device, now: datetime) -> TokenPair:
        await repository.save_device(self.uow.session, device)
        raw = random_token()
        refresh = RefreshToken(
            device_id=device.id,
            token_hash=token_hash(raw),
            created_at=now,
            expires_at=now + timedelta(days=30),
            revoked_at=None,
        )
        await repository.add_refresh(self.uow.session, refresh)
        access = encode_access(
            device.user_id, device.id, self.config.jwt_secret.get_secret_value(), now
        )
        return TokenPair(access_token=access, refresh_token=raw)

    async def refresh(self, raw: str) -> TokenPair:
        """Raise InvalidRefreshError; used tokens never revoke another authorization."""
        digest = token_hash(raw)
        owner = await repository.refresh_owner(self.uow.session, digest)
        if owner is None:
            raise InvalidRefreshError()
        try:
            await self.users.get_account(owner, for_update=True)
        except UserNotFoundError as exc:
            raise InvalidRefreshError() from exc
        token = await repository.get_refresh(self.uow.session, digest)
        now = datetime.now(UTC)
        if token is None or token.revoked_at is not None or token.expires_at <= now:
            raise InvalidRefreshError()
        device = await repository.get_owned_device(self.uow.session, owner, token.device_id)
        if device is None:
            raise InvalidRefreshError()
        token.revoked_at = now
        await repository.flush(self.uow.session)
        return await self._issue(device, now)

    async def devices(self, user_id: UUID, limit: int, offset: int) -> DevicePage:
        """Raise InvalidAccessError for absent account."""
        await self._authenticated_account(user_id)
        rows, total = await repository.list_devices(
            self.uow.session, user_id, datetime.now(UTC), limit, offset
        )
        return DevicePage(
            items=[
                DeviceInfo(
                    id=d.id,
                    created_at=d.created_at,
                    last_authorized_at=d.last_authorized_at,
                    active=active,
                )
                for d, active in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def revoke_device(self, user_id: UUID, device_id: UUID) -> None:
        """Raise InvalidAccessError or DeviceNotFoundError."""
        await self._authenticated_account(user_id, for_update=True)
        device = await repository.get_owned_device(self.uow.session, user_id, device_id)
        if device is None:
            raise DeviceNotFoundError()
        await repository.revoke_device(self.uow.session, device.id, datetime.now(UTC))

    async def logout_everywhere(self, user_id: UUID) -> None:
        """Raise InvalidAccessError for absent account."""
        await self._authenticated_account(user_id, for_update=True)
        await repository.revoke_all(self.uow.session, user_id, datetime.now(UTC))

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> None:
        """Raise InvalidAccessError or InvalidCredentialsError; revoke all refresh atomically."""
        await self._authenticated_account(user_id, for_update=True)
        await self.users.change_password(user_id, current_password, new_password)
        await repository.revoke_all(self.uow.session, user_id, datetime.now(UTC))

    async def register(self, data: CreateUserInput) -> UUID:
        """Raise EmailAlreadyExistsError or AuthorizationConflictError."""
        account = await self.users.create_user(data)
        return await self._reserve_confirmation(account.id)

    async def resend_confirmation(self, email: str, password: str) -> UUID:
        """Raise InvalidCredentialsError or a confirmation or authorization conflict."""
        account = await self.users.verify_credentials(email, password)
        account = await self.users.get_account(account.id, for_update=True)
        account = await self.users.verify_credentials(email, password)
        now = datetime.now(UTC)
        latest = await repository.latest_confirmation(self.uow.session, account.id)
        if account.email_confirmed or (
            latest is not None
            and latest.created_at
            + timedelta(seconds=self.config.confirmation_resend_cooldown_seconds)
            > now
        ):
            raise ConfirmationConflictError()
        await repository.revoke_confirmations(self.uow.session, account.id, now)
        return await self._reserve_confirmation(account.id)

    async def _reserve_confirmation(self, user_id: UUID) -> UUID:
        now = datetime.now(UTC)
        confirmation = EmailConfirmation(
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self.config.confirmation_ttl_seconds),
            consumed_at=None,
            revoked_at=None,
        )
        await repository.add_confirmation(self.uow.session, confirmation)
        return confirmation.id

    async def prepare_confirmation_delivery(
        self, confirmation_id: UUID
    ) -> ConfirmationDelivery | None:
        """Derive the same code on each delivery attempt while the confirmation is active."""
        prepared = await self._confirmation_for_delivery(confirmation_id)
        if prepared is None:
            return None
        confirmation, account = prepared
        return ConfirmationDelivery(
            email=account.email,
            code=self._confirmation_code(confirmation.id),
            created_at=confirmation.created_at,
            expires_at=confirmation.expires_at,
        )

    async def confirmation_delivery_is_current(self, confirmation_id: UUID) -> bool:
        """Check whether the confirmation is still active."""
        return await self._confirmation_for_delivery(confirmation_id) is not None

    async def _confirmation_for_delivery(
        self, confirmation_id: UUID
    ) -> tuple[EmailConfirmation, UserState] | None:
        confirmation = await repository.get_confirmation_by_id(self.uow.session, confirmation_id)
        if (
            confirmation is None
            or confirmation.consumed_at is not None
            or confirmation.revoked_at is not None
            or confirmation.expires_at <= datetime.now(UTC)
        ):
            return None
        try:
            account = await self.users.get_account(confirmation.user_id)
        except UserNotFoundError:
            return None
        if account.email_confirmed:
            return None
        return confirmation, account

    def _confirmation_code(self, confirmation_id: UUID) -> str:
        return confirmation_token(
            confirmation_id, self.config.confirmation_secret.get_secret_value()
        )

    async def confirm_email(self, email: str, raw: str) -> TokenPair:
        """Raise InvalidConfirmationError or DeviceLimitError; all changes atomic."""
        try:
            account = await self.users.get_account_by_email(email)
            account = await self.users.get_account(account.id, for_update=True)
        except UserNotFoundError as exc:
            raise InvalidConfirmationError() from exc
        if account.email_confirmed:
            raise InvalidConfirmationError()
        confirmation = await repository.get_current_confirmation(self.uow.session, account.id)
        now = datetime.now(UTC)
        if (
            confirmation is None
            or confirmation.expires_at <= now
            or not raw.isascii()
            or not compare_digest(raw, self._confirmation_code(confirmation.id))
        ):
            raise InvalidConfirmationError()
        confirmation.consumed_at = now
        await self.users.confirm_email(account.id)
        result = await self._authorize(account.id, now)
        await repository.flush(self.uow.session)
        return result
