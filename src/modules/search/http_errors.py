from src.core.http_errors import HttpErrorResponse, map_error
from src.modules.search.errors import (
    SearchCacheUnavailableError,
    SearchInvalidResponseError,
    SearchUnavailableError,
)

ERROR_MAPPINGS = (
    map_error(SearchUnavailableError, HttpErrorResponse(503, "Dictionary service unavailable")),
    map_error(SearchInvalidResponseError, HttpErrorResponse(502, "Invalid dictionary response")),
    map_error(SearchCacheUnavailableError, HttpErrorResponse(503, "Search cache unavailable")),
)
