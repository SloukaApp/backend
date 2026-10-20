import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from src.core.errors import ApplicationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HttpErrorResponse:
    status_code: int
    detail: str
    headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not 400 <= self.status_code <= 599:
            raise ValueError("An HTTP error response must have a 4xx or 5xx status")


@dataclass(frozen=True, slots=True)
class ErrorMapping:
    error_type: type[ApplicationError]
    translate: Callable[[ApplicationError], HttpErrorResponse]


def map_error[E: ApplicationError](
    error_type: type[E],
    response: HttpErrorResponse | Callable[[E], HttpErrorResponse],
) -> ErrorMapping:
    """Adapt a static response or a typed translator to the shared registry."""

    def translate(error: ApplicationError) -> HttpErrorResponse:
        if not isinstance(error, error_type):
            raise TypeError("The error does not match the registered mapping")
        if isinstance(response, HttpErrorResponse):
            return response
        return response(error)

    return ErrorMapping(error_type, translate)


def build_application_error_handler(
    *mappings: ErrorMapping,
) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    """Build an application-local registry snapshot with exact exception matching."""
    registry: dict[type[ApplicationError], ErrorMapping] = {}
    for mapping in mappings:
        if mapping.error_type in registry:
            raise ValueError("Duplicate application error mapping")
        registry[mapping.error_type] = mapping

    async def handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, ApplicationError):
            mapping = registry.get(type(exc))
            if mapping is not None:
                response = mapping.translate(exc)
                return JSONResponse(
                    status_code=response.status_code,
                    content={"detail": response.detail},
                    headers=response.headers,
                )

        # Exception messages and arguments can contain credentials or personal data.
        logger.error("Unhandled error type: %s.%s", type(exc).__module__, type(exc).__qualname__)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return handler
