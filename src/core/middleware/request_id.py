from uuid import uuid7

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.core.request_context import request_id_scope

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid7().hex
        with request_id_scope(request_id):
            response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
