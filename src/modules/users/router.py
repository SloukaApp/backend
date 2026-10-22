from typing import Annotated

from fastapi import APIRouter, Depends

from src.core.dependencies import UoWDep
from src.core.schemas import ErrorResponse
from src.modules.auth.dependencies import get_current_user
from src.modules.users.dependencies import UsersServiceDep
from src.modules.users.dto import UpdateProfileInput, UserState
from src.modules.users.schemas import ProfileResponse, UpdateProfileRequest

router = APIRouter(prefix="/users", tags=["users"])
CurrentUserDep = Annotated[UserState, Depends(get_current_user)]


@router.get(
    "/me",
    response_model=ProfileResponse,
    responses={401: {"model": ErrorResponse}},
)
async def read_profile(
    user: CurrentUserDep, service: UsersServiceDep, uow: UoWDep
) -> ProfileResponse:
    async with uow:
        result = await service.get_account(user.id)
        return ProfileResponse(**result.model_dump())


@router.patch(
    "/me",
    response_model=ProfileResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def update_profile(
    data: UpdateProfileRequest,
    user: CurrentUserDep,
    service: UsersServiceDep,
    uow: UoWDep,
) -> ProfileResponse:
    async with uow:
        result = await service.update_profile(
            user.id, UpdateProfileInput(**data.model_dump(exclude_unset=True))
        )
        return ProfileResponse(**result.model_dump())


@router.post(
    "/me/onboarding",
    response_model=ProfileResponse,
    responses={401: {"model": ErrorResponse}},
)
async def complete_onboarding(
    user: CurrentUserDep, service: UsersServiceDep, uow: UoWDep
) -> ProfileResponse:
    async with uow:
        result = await service.complete_onboarding(user.id)
        return ProfileResponse(**result.model_dump())
