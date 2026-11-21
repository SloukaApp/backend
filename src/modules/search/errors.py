from src.core.errors import ApplicationError


class SearchUnavailableError(ApplicationError):
    pass


class SearchInvalidResponseError(ApplicationError):
    pass


class SearchCacheUnavailableError(ApplicationError):
    pass
