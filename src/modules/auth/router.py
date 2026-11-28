from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.core.dependencies import UoWDep
from src.core.http_errors import error_responses
from src.modules.auth.dependencies import (
    AuthServiceDep,
    ConfirmationQueueDep,
    PasswordResetQueueDep,
    PrincipalDep,
    check_confirmation,
    check_login,
    check_password_reset,
)
from src.modules.auth.dto import PasswordResetInput
from src.modules.auth.schemas import (
    ConfirmationRequest,
    CredentialsRequest,
    DeliveryResponse,
    DevicesResponse,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    RefreshRequest,
    RegistrationRequest,
    TokenResponse,
)
from src.modules.users.dto import CreateUserInput

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=DeliveryResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
async def register(
    data: RegistrationRequest, uow: UoWDep, service: AuthServiceDep, queue: ConfirmationQueueDep
) -> DeliveryResponse:
    async with uow:
        confirmation_id = await service.register(CreateUserInput(**data.model_dump()))
    await queue.enqueue(confirmation_id)
    return DeliveryResponse()


@router.post(
    "/confirmations/resend",
    response_model=DeliveryResponse,
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
async def resend(
    data: CredentialsRequest, uow: UoWDep, service: AuthServiceDep, queue: ConfirmationQueueDep
) -> DeliveryResponse:
    async with uow:
        confirmation_id = await service.resend_confirmation(data.email, data.password)
    await queue.enqueue(confirmation_id)
    return DeliveryResponse()


@router.post(
    "/confirm-email",
    dependencies=[Depends(check_confirmation)],
    response_model=TokenResponse,
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
async def confirm(data: ConfirmationRequest, uow: UoWDep, service: AuthServiceDep) -> TokenResponse:
    async with uow:
        result = await service.confirm_email(data.email, data.token)
        return TokenResponse(**result.model_dump())


@router.post(
    "/login",
    dependencies=[Depends(check_login)],
    response_model=TokenResponse,
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ),
)
async def login(data: CredentialsRequest, uow: UoWDep, service: AuthServiceDep) -> TokenResponse:
    async with uow:
        result = await service.login(data.email, data.password)
        return TokenResponse(**result.model_dump())


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    ),
)
async def refresh(data: RefreshRequest, uow: UoWDep, service: AuthServiceDep) -> TokenResponse:
    async with uow:
        result = await service.refresh(data.refresh_token)
        return TokenResponse(**result.model_dump())


@router.get(
    "/devices",
    response_model=DevicesResponse,
    responses=error_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_CONTENT),
)
async def devices(
    principal: PrincipalDep,
    uow: UoWDep,
    service: AuthServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DevicesResponse:
    async with uow:
        result = await service.devices(principal.user_id, limit, offset)
        return DevicesResponse(**result.model_dump())


@router.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    ),
)
async def revoke_device(
    device_id: UUID, principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.revoke_device(principal.user_id, device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND),
)
async def logout(principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep) -> Response:
    async with uow:
        await service.revoke_device(principal.user_id, principal.device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(status.HTTP_401_UNAUTHORIZED),
)
async def logout_everywhere(
    principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.logout_everywhere(principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_CONTENT),
)
async def change_password(
    data: PasswordChangeRequest, principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.change_password(principal.user_id, data.current_password, data.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PasswordResetResponse,
    responses=error_responses(status.HTTP_422_UNPROCESSABLE_CONTENT),
)
async def request_password_reset(
    data: PasswordResetRequest, uow: UoWDep, service: AuthServiceDep, queue: PasswordResetQueueDep
) -> PasswordResetResponse:
    async with uow:
        reset_id = await service.request_password_reset(data.email)
    await queue.enqueue_password_reset(reset_id)
    return PasswordResetResponse()


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_password_reset)],
    responses=error_responses(status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_CONTENT),
)
async def confirm_password_reset(
    data: PasswordResetConfirm, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.confirm_password_reset(PasswordResetInput(**data.model_dump()))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
