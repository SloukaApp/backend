from starlette._utils import get_route_path
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.core.config import API_V1_PREFIX, RateLimitConfig
from src.core.dependencies import get_client_ip, get_redis
from src.core.rate_limit import RateLimiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, config: RateLimitConfig, key_prefix: str) -> None:
        super().__init__(app)
        self.key_prefix = key_prefix
        self.default_budget = (config.api_ip_window_seconds, config.api_ip_max_requests)
        self.route_budgets = {
            ("GET", f"{API_V1_PREFIX}/search"): (
                "search:ip",
                config.search_ip_window_seconds,
                config.search_ip_max_requests,
            ),
            ("POST", f"{API_V1_PREFIX}/auth/login"): (
                "login:ip",
                config.login_ip_window_seconds,
                config.login_ip_max_attempts,
            ),
            ("POST", f"{API_V1_PREFIX}/auth/confirm-email"): (
                "confirmation:ip",
                config.confirmation_ip_window_seconds,
                config.confirmation_ip_max_attempts,
            ),
        }
        # OpenAPI also serves as the deployment health probe.
        self.exempt_routes = {
            (method, f"{API_V1_PREFIX}/{path}")
            for method in ("GET", "HEAD")
            for path in ("openapi.json", "docs")
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = get_route_path(request.scope)
        route = (request.method, path)
        is_api_path = path == API_V1_PREFIX or path.startswith(f"{API_V1_PREFIX}/")
        if not is_api_path or route in self.exempt_routes:
            return await call_next(request)

        ip = get_client_ip(request)
        budgets = [(f"api:ip:{ip}", *self.default_budget)]
        route_budget = self.route_budgets.get(route)
        if route_budget is not None:
            subject, window, maximum = route_budget
            budgets.append((f"{subject}:{ip}", window, maximum))
        limiter = RateLimiter(get_redis(request), self.key_prefix)
        await limiter.check_many(budgets)
        return await call_next(request)
