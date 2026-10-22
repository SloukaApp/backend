from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.dependencies import SettingsDep, UoWDep
from src.modules.auth.adapters import ConfirmationMailer
from src.modules.auth.dto import Principal
from src.modules.auth.errors import EmailUnconfirmedError, InvalidAccessError
from src.modules.auth.service import AuthService
from src.modules.users.dependencies import UsersServiceDep
from src.modules.users.dto import UserState

bearer = HTTPBearer(auto_error=False)


def get_auth_service(
    uow: UoWDep, users: UsersServiceDep, settings: SettingsDep, request: Request
) -> AuthService:
    mailer = cast(ConfirmationMailer, request.app.state.confirmation_mailer)
    return AuthService(uow, users, settings.auth, mailer)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_principal(
    uow: UoWDep,
    service: AuthServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None:
        raise InvalidAccessError()
    async with uow:
        principal, _ = await service.authenticate(credentials.credentials)
        return principal


async def get_current_user(
    uow: UoWDep,
    service: AuthServiceDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserState:
    if credentials is None:
        raise InvalidAccessError()
    async with uow:
        _, account = await service.authenticate(credentials.credentials)
        return account


async def get_confirmed_user(account: Annotated[UserState, Depends(get_current_user)]) -> UserState:
    if not account.email_confirmed:
        raise EmailUnconfirmedError()
    return account


PrincipalDep = Annotated[Principal, Depends(get_principal)]
