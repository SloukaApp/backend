from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.core import http_errors as core_http
from src.core.config import API_V1_PREFIX, get_settings
from src.core.db import build_engine, build_session_factory
from src.core.logging import setup_logging
from src.core.middleware.error_handling import ErrorHandlingMiddleware
from src.core.middleware.rate_limit import RateLimitMiddleware
from src.core.middleware.request_id import RequestIdMiddleware
from src.core.redis import build_redis
from src.modules.auth import http_errors as auth_http
from src.modules.auth.router import router as auth_router
from src.modules.search import http_errors as search_http
from src.modules.search.router import router as search_router
from src.modules.search.verbum import VerbumClient
from src.modules.users import http_errors as users_http
from src.modules.users.router import router as users_router
from src.worker.broker import build_broker
from src.worker.queue import TaskiqConfirmationQueue


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    async with AsyncExitStack() as cleanup:
        engine = build_engine(settings.db)
        cleanup.push_async_callback(engine.dispose)
        redis = build_redis(settings.redis)
        cleanup.push_async_callback(redis.aclose)

        broker = build_broker(settings.redis)
        cleanup.push_async_callback(broker.shutdown)
        app.state.confirmation_queue = TaskiqConfirmationQueue(
            broker, settings.redis.socket_timeout
        )

        app.state.session_factory = build_session_factory(engine)
        app.state.redis = redis
        http = await cleanup.enter_async_context(
            httpx.AsyncClient(
                timeout=httpx.Timeout(
                    settings.verbum.read_timeout_seconds,
                    connect=settings.verbum.connect_timeout_seconds,
                ),
                follow_redirects=False,
            )
        )
        app.state.verbum_client = VerbumClient(http, settings.verbum)
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
        exception_handlers={
            **core_http.EXCEPTION_HANDLERS,
            **auth_http.EXCEPTION_HANDLERS,
            **search_http.EXCEPTION_HANDLERS,
            **users_http.EXCEPTION_HANDLERS,
        },
    )

    # The last middleware added runs first on incoming requests.
    app.add_middleware(
        RateLimitMiddleware, config=settings.rate_limit, key_prefix=settings.redis.key_prefix
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.app.trusted_proxies)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.add_middleware(RequestIdMiddleware)

    api_router = APIRouter(
        prefix=API_V1_PREFIX,
        responses=core_http.error_responses(
            status.HTTP_429_TOO_MANY_REQUESTS,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ),
    )
    api_router.include_router(auth_router)
    api_router.include_router(users_router)
    api_router.include_router(search_router)
    app.include_router(api_router)
    return app
