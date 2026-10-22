from typing import Annotated

from fastapi import Depends

from src.core.dependencies import UoWDep
from src.modules.users.service import UsersService


def get_users_service(uow: UoWDep) -> UsersService:
    return UsersService(uow)


UsersServiceDep = Annotated[UsersService, Depends(get_users_service)]
