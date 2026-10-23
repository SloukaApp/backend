from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.core.config import API_V1_PREFIX, get_settings
from src.core.db import build_engine, build_session_factory
from src.core.errors import ApplicationError
from src.core.http_errors import ERROR_MAPPINGS as CORE_ERROR_MAPPINGS
from src.core.http_errors import build_application_error_handler
from src.core.logging import RequestIdMiddleware, setup_logging
from src.core.redis import build_redis
from src.modules.auth.adapters import SmtpConfirmationMailer
from src.modules.auth.http_errors import ERROR_MAPPINGS as AUTH_ERROR_MAPPINGS
from src.modules.auth.router import router as auth_router
from src.modules.users.http_errors import ERROR_MAPPINGS as USERS_ERROR_MAPPINGS
from src.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    async with AsyncExitStack() as cleanup:
        engine = build_engine(settings.db)
        cleanup.push_async_callback(engine.dispose)
        redis = build_redis(settings.redis)
        cleanup.push_async_callback(redis.aclose)

        mailer = SmtpConfirmationMailer(settings.smtp)
        cleanup.push_async_callback(mailer.close)
        app.state.confirmation_mailer = mailer

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
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.app.trusted_proxies)
    error_handler = build_application_error_handler(
        *CORE_ERROR_MAPPINGS, *USERS_ERROR_MAPPINGS, *AUTH_ERROR_MAPPINGS
    )
    app.add_exception_handler(ApplicationError, error_handler)
    app.add_exception_handler(Exception, error_handler)

    api_router = APIRouter(prefix=API_V1_PREFIX)
    api_router.include_router(auth_router)
    api_router.include_router(users_router)
    app.include_router(api_router)
    return app
