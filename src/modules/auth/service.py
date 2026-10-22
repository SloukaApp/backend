from datetime import UTC, datetime, timedelta
from uuid import UUID

from src.core.config import AuthConfig
from src.core.uow import UnitOfWork
from src.modules.auth import repository
from src.modules.auth.adapters import ConfirmationMailer, decode_access
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
from src.modules.users.errors import UserNotFoundError
from src.modules.users.service import UsersService


class AuthService:
    """Own auth workflows; dependency direction is auth → users. Shared operation UoW."""

    def __init__(
        self, uow: UnitOfWork, users: UsersService, config: AuthConfig, mailer: ConfirmationMailer
    ) -> None:
        self.uow = uow
        self.users = users
        self.config = config
        self.mailer = mailer

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

    async def login(self, email: str, password: str, installation_id: UUID) -> TokenPair:
        """Raise InvalidCredentialsError, EmailUnconfirmedError, DeviceLimitError."""
        account = await self.users.verify_credentials(email, password)
        account = await self.users.get_account(account.id, for_update=True)
        account = await self.users.verify_credentials(email, password)
        if not account.email_confirmed:
            raise EmailUnconfirmedError()
        return await self._authorize(account.id, installation_id, datetime.now(UTC))

    async def _authorize(self, user_id: UUID, installation_id: UUID, now: datetime) -> TokenPair:
        device = await repository.get_device(self.uow.session, user_id, installation_id)
        current = await repository.current_refresh(self.uow.session, device.id) if device else None
        already_active = current is not None and current.expires_at > now
        count = await repository.active_device_count(self.uow.session, user_id, now)
        if not already_active and count >= self.config.max_active_devices:
            raise DeviceLimitError()
        if current is not None:
            current.revoked_at = now
            await repository.flush(self.uow.session)
        if device is None:
            device = Device(
                user_id=user_id,
                installation_id=installation_id,
                created_at=now,
                last_authorized_at=now,
            )
        else:
            device.last_authorized_at = now
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
                    installation_id=d.installation_id,
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

    async def register(self, data: CreateUserInput) -> ConfirmationDelivery:
        """Raise EmailAlreadyExistsError; delivery DTO is private, never an HTTP response."""
        account = await self.users.create_user(data)
        return await self._prepare_confirmation(account)

    async def resend_confirmation(self, email: str, password: str) -> ConfirmationDelivery:
        """Raise InvalidCredentialsError or ConfirmationConflictError."""
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
        return await self._prepare_confirmation(account)

    async def _prepare_confirmation(self, account: UserState) -> ConfirmationDelivery:
        now = datetime.now(UTC)
        raw = confirmation_token()
        await repository.add_confirmation(
            self.uow.session,
            EmailConfirmation(
                user_id=account.id,
                token_hash=token_hash(raw),
                created_at=now,
                expires_at=now + timedelta(seconds=self.config.confirmation_ttl_seconds),
                consumed_at=None,
                revoked_at=None,
            ),
        )
        return ConfirmationDelivery(email=account.email, token=raw)

    async def deliver_confirmation(self, delivery: ConfirmationDelivery) -> None:
        """Call only outside a transaction; raise MailDeliveryError after persisted registration."""
        await self.mailer.send_confirmation(delivery.email, delivery.token)

    async def confirm_email(self, raw: str, installation_id: UUID) -> TokenPair:
        """Raise InvalidConfirmationError or DeviceLimitError; all changes atomic."""
        digest = token_hash(raw)
        owner = await repository.confirmation_owner(self.uow.session, digest)
        if owner is None:
            raise InvalidConfirmationError()
        try:
            await self.users.get_account(owner, for_update=True)
        except UserNotFoundError as exc:
            raise InvalidConfirmationError() from exc
        confirmation = await repository.get_confirmation(self.uow.session, digest)
        now = datetime.now(UTC)
        if (
            confirmation is None
            or confirmation.consumed_at is not None
            or confirmation.revoked_at is not None
            or confirmation.expires_at <= now
        ):
            raise InvalidConfirmationError()
        confirmation.consumed_at = now
        await self.users.confirm_email(owner)
        result = await self._authorize(owner, installation_id, now)
        await repository.flush(self.uow.session)
        return result
