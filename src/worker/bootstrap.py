from contextlib import AsyncExitStack
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from taskiq import AsyncBroker

from src.core.config import Settings, get_settings
from src.core.db import build_engine, build_session_factory
from src.core.redis import build_redis
from src.worker.broker import build_broker


@dataclass(slots=True, frozen=True)
class WorkerDependencies:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    broker: AsyncBroker


async def build_worker_dependencies() -> WorkerDependencies:
    settings = get_settings()
    async with AsyncExitStack() as cleanup:
        engine = build_engine(settings.db)
        cleanup.push_async_callback(engine.dispose)
        session_factory = build_session_factory(engine)
        redis = build_redis(settings.redis)
        cleanup.push_async_callback(redis.aclose)
        broker = build_broker(settings)
        dependencies = WorkerDependencies(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            redis=redis,
            broker=broker,
        )
        cleanup.pop_all()
        return dependencies


async def shutdown_worker_dependencies(dependencies: WorkerDependencies) -> None:
    async with AsyncExitStack() as cleanup:
        cleanup.push_async_callback(dependencies.engine.dispose)
        cleanup.push_async_callback(dependencies.redis.aclose)
        cleanup.push_async_callback(dependencies.broker.shutdown)
