from starlette.exceptions import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.errors import RateLimitExceededError, RateLimitUnavailableError
from src.core.http_errors import (
    handle_http_exception,
    handle_internal_error,
    handle_rate_limit_exceeded,
    handle_rate_limit_unavailable,
)


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except RateLimitExceededError as exc:
            return await handle_rate_limit_exceeded(request, exc)
        except RateLimitUnavailableError as exc:
            return await handle_rate_limit_unavailable(request, exc)
        except HTTPException as exc:
            return await handle_http_exception(request, exc)
        except Exception as exc:
            return await handle_internal_error(request, exc)
