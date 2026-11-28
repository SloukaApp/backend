from fastapi import Request, status
from fastapi.responses import JSONResponse

from src.core.http_errors import ExceptionHandlers, error_response
from src.modules.search.errors import (
    SearchCacheUnavailableError,
    SearchInvalidResponseError,
    SearchUnavailableError,
)


async def handle_search_unavailable(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "Dictionary service unavailable")


async def handle_search_invalid_response(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_502_BAD_GATEWAY, "Invalid dictionary response")


async def handle_search_cache_unavailable(_request: Request, _exc: Exception) -> JSONResponse:
    return error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "Search cache unavailable")


EXCEPTION_HANDLERS: ExceptionHandlers = {
    SearchCacheUnavailableError: handle_search_cache_unavailable,
    SearchInvalidResponseError: handle_search_invalid_response,
    SearchUnavailableError: handle_search_unavailable,
}
