class ApplicationError(Exception):
    """An expected operation failure, independent of its delivery transport."""


class RateLimitExceededError(ApplicationError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__()


class RateLimitUnavailableError(ApplicationError):
    pass
