from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from src.core.dependencies import UoWDep
from src.core.schemas import ErrorResponse
from src.modules.auth.dependencies import AuthServiceDep, PrincipalDep
from src.modules.auth.schemas import (
    ConfirmationRequest,
    CredentialsRequest,
    DeliveryResponse,
    DevicesResponse,
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegistrationRequest,
    TokenResponse,
)
from src.modules.users.dto import CreateUserInput

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=DeliveryResponse,
    status_code=201,
    responses={code: {"model": ErrorResponse} for code in (409, 422, 503)},
)
async def register(
    data: RegistrationRequest, uow: UoWDep, service: AuthServiceDep
) -> DeliveryResponse:
    async with uow:
        delivery = await service.register(CreateUserInput(**data.model_dump()))
    await service.deliver_confirmation(delivery)
    return DeliveryResponse()


@router.post(
    "/confirmations/resend",
    response_model=DeliveryResponse,
    responses={code: {"model": ErrorResponse} for code in (401, 409, 422, 503)},
)
async def resend(
    data: CredentialsRequest, uow: UoWDep, service: AuthServiceDep
) -> DeliveryResponse:
    async with uow:
        delivery = await service.resend_confirmation(data.email, data.password)
    await service.deliver_confirmation(delivery)
    return DeliveryResponse()


@router.post(
    "/confirm-email",
    response_model=TokenResponse,
    responses={code: {"model": ErrorResponse} for code in (401, 409, 422)},
)
async def confirm(data: ConfirmationRequest, uow: UoWDep, service: AuthServiceDep) -> TokenResponse:
    async with uow:
        result = await service.confirm_email(data.token, data.installation_id)
        return TokenResponse(**result.model_dump())


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={code: {"model": ErrorResponse} for code in (401, 403, 409, 422)},
)
async def login(data: LoginRequest, uow: UoWDep, service: AuthServiceDep) -> TokenResponse:
    async with uow:
        result = await service.login(data.email, data.password, data.installation_id)
        return TokenResponse(**result.model_dump())


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={code: {"model": ErrorResponse} for code in (401, 409, 422)},
)
async def refresh(data: RefreshRequest, uow: UoWDep, service: AuthServiceDep) -> TokenResponse:
    async with uow:
        result = await service.refresh(data.refresh_token)
        return TokenResponse(**result.model_dump())


@router.get(
    "/devices",
    response_model=DevicesResponse,
    responses={code: {"model": ErrorResponse} for code in (401, 422)},
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
    status_code=204,
    responses={code: {"model": ErrorResponse} for code in (401, 404, 422)},
)
async def revoke_device(
    device_id: UUID, principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.revoke_device(principal.user_id, device_id)
    return Response(status_code=204)


@router.post(
    "/logout",
    status_code=204,
    responses={code: {"model": ErrorResponse} for code in (401, 404, 422)},
)
async def logout(principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep) -> Response:
    async with uow:
        await service.revoke_device(principal.user_id, principal.device_id)
    return Response(status_code=204)


@router.post(
    "/logout-everywhere",
    status_code=204,
    responses={code: {"model": ErrorResponse} for code in (401,)},
)
async def logout_everywhere(
    principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.logout_everywhere(principal.user_id)
    return Response(status_code=204)


@router.post(
    "/password",
    status_code=204,
    responses={code: {"model": ErrorResponse} for code in (401, 422)},
)
async def change_password(
    data: PasswordChangeRequest, principal: PrincipalDep, uow: UoWDep, service: AuthServiceDep
) -> Response:
    async with uow:
        await service.change_password(principal.user_id, data.current_password, data.new_password)
    return Response(status_code=204)
