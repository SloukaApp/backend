"""Auth budgets; subjects deliberately contain email/IP per the agreed policy."""

from src.core.config import RateLimitConfig
from src.core.rate_limit import RateLimiter


class AuthRateLimits:
    def __init__(self, limiter: RateLimiter, config: RateLimitConfig) -> None:
        self.limiter = limiter
        self.config = config

    async def confirmation(self, email: str, ip: str) -> None:
        await self.limiter.check_many(
            [
                (
                    f"confirmation:ip:{ip}",
                    self.config.confirmation_ip_window_seconds,
                    self.config.confirmation_ip_max_attempts,
                ),
                (
                    f"confirmation:email:{email}",
                    self.config.confirmation_email_window_seconds,
                    self.config.confirmation_email_max_attempts,
                ),
            ]
        )

    async def login(self, email: str, ip: str) -> None:
        await self.limiter.check_many(
            [
                (
                    f"login:ip:{ip}",
                    self.config.login_ip_window_seconds,
                    self.config.login_ip_max_attempts,
                ),
                (
                    f"login:account_ip:{len(email)}:{email}:{ip}",
                    self.config.login_window_seconds,
                    self.config.login_max_attempts,
                ),
            ]
        )
