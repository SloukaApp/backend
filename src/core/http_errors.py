import logging
from collections.abc import Callable, Coroutine, Mapping
from http import HTTPStatus
from typing import cast

from fastapi import Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException

from src.core.errors import RateLimitExceededError, RateLimitUnavailableError
from src.core.schemas import ErrorResponse

logger = logging.getLogger(__name__)

type ExceptionHandlers = dict[
    int | type[Exception], Callable[[Request, Exception], Coroutine[object, object, Response]]
]


def error_response(
    status_code: int, detail: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(detail=detail).model_dump(),
        headers=headers,
    )


def error_responses(*status_codes: int) -> dict[int | str, dict[str, object]]:
    responses: dict[int | str, dict[str, object]] = {
        code: {"model": ErrorResponse} for code in status_codes
    }
    if status.HTTP_429_TOO_MANY_REQUESTS in responses:
        responses[status.HTTP_429_TOO_MANY_REQUESTS]["headers"] = {
            "Retry-After": {
                "description": "Seconds until the client can retry",
                "schema": {"type": "integer", "minimum": 1},
            }
        }
    return responses


async def handle_request_validation(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid request")


async def handle_http_exception(_request: Request, exc: Exception) -> Response:
    error = cast(HTTPException, exc)
    headers = {
        name: value
        for name, value in (error.headers or {}).items()
        if name.lower() in {"allow", "retry-after", "www-authenticate"}
    }
    if not is_body_allowed_for_status_code(error.status_code):
        return Response(status_code=error.status_code, headers=headers)
    try:
        detail = HTTPStatus(error.status_code).phrase
    except ValueError:
        detail = "Request failed"
    return error_response(error.status_code, detail, headers)


async def handle_internal_error(_request: Request, exc: Exception) -> JSONResponse:
    # Exception messages and arguments can contain credentials or personal data.
    logger.error("Unhandled error type: %s.%s", type(exc).__module__, type(exc).__qualname__)
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error")


async def handle_rate_limit_exceeded(_request: Request, exc: Exception) -> JSONResponse:
    error = cast(RateLimitExceededError, exc)
    return error_response(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many requests",
        {"Retry-After": str(error.retry_after_seconds)},
    )


async def handle_rate_limit_unavailable(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "Rate limit service unavailable")


EXCEPTION_HANDLERS: ExceptionHandlers = {
    Exception: handle_internal_error,
    HTTPException: handle_http_exception,
    RequestValidationError: handle_request_validation,
    RateLimitExceededError: handle_rate_limit_exceeded,
    RateLimitUnavailableError: handle_rate_limit_unavailable,
}
