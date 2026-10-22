from src.core.errors import ApplicationError


class InvalidAccessError(ApplicationError):
    pass


class InvalidRefreshError(ApplicationError):
    pass


class InvalidConfirmationError(ApplicationError):
    pass


class EmailUnconfirmedError(ApplicationError):
    pass


class DeviceLimitError(ApplicationError):
    pass


class DeviceNotFoundError(ApplicationError):
    pass


class ConfirmationConflictError(ApplicationError):
    pass


class MailDeliveryError(ApplicationError):
    pass


class AuthorizationConflictError(ApplicationError):
    pass
