from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings, get_settings
from src.core.uow import UnitOfWork


def get_uow(request: Request) -> UnitOfWork:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return UnitOfWork(session_factory)


def get_redis(request: Request) -> Redis:
    redis: Redis = request.app.state.redis
    return redis


UoWDep = Annotated[UnitOfWork, Depends(get_uow)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]
