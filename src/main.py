from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import API_V1_PREFIX, get_settings
from src.core.db import build_engine, build_session_factory
from src.core.errors import ApplicationError
from src.core.http_errors import build_application_error_handler
from src.core.logging import RequestIdMiddleware, setup_logging
from src.core.redis import build_redis


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    async with AsyncExitStack() as cleanup:
        engine = build_engine(settings.db)
        cleanup.push_async_callback(engine.dispose)
        redis = build_redis(settings.redis)
        cleanup.push_async_callback(redis.aclose)

        app.state.session_factory = build_session_factory(engine)
        app.state.redis = redis
        yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.logging.level)

    app = FastAPI(
        title="Slouka API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    # Pass module HTTP mappings here as their operations are implemented.
    error_handler = build_application_error_handler()
    app.add_exception_handler(ApplicationError, error_handler)
    app.add_exception_handler(Exception, error_handler)

    api_router = APIRouter(prefix=API_V1_PREFIX)
    app.include_router(api_router)
    return app
